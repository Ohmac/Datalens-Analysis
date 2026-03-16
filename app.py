import os
import json
import uuid

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(24))


@app.template_filter("format_number")
def format_number(value: int) -> str:
    """Jinja filter: format an integer with thousands separators."""
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
ALLOWED_EXTENSIONS = {"csv"}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def load_dataframe(filename: str) -> pd.DataFrame:
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    return pd.read_csv(filepath)


def safe_filename_for_session(original: str) -> str:
    """Return a UUID-based filename that preserves the .csv extension."""
    ext = os.path.splitext(secure_filename(original))[1]
    return f"{uuid.uuid4().hex}{ext}"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    filename = session.get("filename")
    has_data = filename is not None and os.path.exists(
        os.path.join(app.config["UPLOAD_FOLDER"], filename)
    )
    return render_template("index.html", has_data=has_data)


@app.route("/upload", methods=["GET", "POST"])
def upload():
    if request.method == "POST":
        if "file" not in request.files:
            flash("No file part in the request.", "danger")
            return redirect(request.url)

        file = request.files["file"]
        if file.filename == "":
            flash("No file selected.", "danger")
            return redirect(request.url)

        if not allowed_file(file.filename):
            flash("Only CSV files are supported.", "danger")
            return redirect(request.url)

        filename = safe_filename_for_session(file.filename)
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(filepath)

        # Quick validation: ensure file is a parseable CSV
        try:
            df = pd.read_csv(filepath)
            if df.empty:
                os.remove(filepath)
                flash("The uploaded CSV file is empty.", "danger")
                return redirect(request.url)
        except Exception:
            os.remove(filepath)
            flash("Could not parse the uploaded file as CSV.", "danger")
            return redirect(request.url)

        # Remove previous upload for this session
        old = session.get("filename")
        if old:
            old_path = os.path.join(app.config["UPLOAD_FOLDER"], old)
            if os.path.exists(old_path):
                os.remove(old_path)

        session["filename"] = filename
        session["original_name"] = secure_filename(file.filename)
        flash("File uploaded successfully!", "success")
        return redirect(url_for("dashboard"))

    return render_template("upload.html")


@app.route("/dashboard")
def dashboard():
    filename = session.get("filename")
    if not filename:
        flash("Please upload a CSV file first.", "warning")
        return redirect(url_for("upload"))

    try:
        df = load_dataframe(filename)
    except Exception:
        flash("Could not load the data file. Please upload again.", "danger")
        return redirect(url_for("upload"))

    num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    cat_cols = df.select_dtypes(include=["string", "object", "category"]).columns.tolist()

    summary = {
        "rows": len(df),
        "columns": len(df.columns),
        "numeric_columns": len(num_cols),
        "categorical_columns": len(cat_cols),
        "missing_values": int(df.isnull().sum().sum()),
        "original_name": session.get("original_name", filename),
    }

    return render_template(
        "dashboard.html",
        summary=summary,
        columns=df.columns.tolist(),
        num_cols=num_cols,
        cat_cols=cat_cols,
    )


@app.route("/analysis")
def analysis():
    filename = session.get("filename")
    if not filename:
        flash("Please upload a CSV file first.", "warning")
        return redirect(url_for("upload"))

    try:
        df = load_dataframe(filename)
    except Exception:
        flash("Could not load the data file. Please upload again.", "danger")
        return redirect(url_for("upload"))

    num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    cat_cols = df.select_dtypes(include=["string", "object", "category"]).columns.tolist()

    # Descriptive statistics for numeric columns
    stats_html = ""
    if num_cols:
        stats_df = df[num_cols].describe().round(4)
        stats_html = stats_df.to_html(classes="table table-sm table-striped", border=0)

    return render_template(
        "analysis.html",
        stats_html=stats_html,
        num_cols=num_cols,
        cat_cols=cat_cols,
        columns=df.columns.tolist(),
    )


# ---------------------------------------------------------------------------
# API endpoints (JSON)
# ---------------------------------------------------------------------------


@app.route("/api/chart", methods=["POST"])
def api_chart():
    filename = session.get("filename")
    if not filename:
        return jsonify({"error": "No data loaded"}), 400

    try:
        df = load_dataframe(filename)
    except Exception:
        return jsonify({"error": "Could not load data"}), 500

    data = request.get_json(silent=True) or {}
    chart_type = data.get("chart_type", "histogram")
    x_col = data.get("x")
    y_col = data.get("y")
    color_col = data.get("color")

    # Validate column names against actual dataframe columns
    valid_cols = set(df.columns.tolist())
    if x_col and x_col not in valid_cols:
        return jsonify({"error": f"Column '{x_col}' not found"}), 400
    if y_col and y_col not in valid_cols:
        return jsonify({"error": f"Column '{y_col}' not found"}), 400
    if color_col and color_col not in valid_cols:
        return jsonify({"error": f"Column '{color_col}' not found"}), 400

    try:
        fig = _build_figure(df, chart_type, x_col, y_col, color_col)
        return jsonify(json.loads(fig.to_json()))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


def _build_figure(
    df: pd.DataFrame,
    chart_type: str,
    x_col: str | None,
    y_col: str | None,
    color_col: str | None,
) -> go.Figure:
    kwargs = {}
    if color_col:
        kwargs["color"] = color_col

    if chart_type == "histogram":
        if not x_col:
            raise ValueError("x column is required for histogram")
        fig = px.histogram(df, x=x_col, **kwargs, title=f"Histogram of {x_col}")

    elif chart_type == "scatter":
        if not x_col or not y_col:
            raise ValueError("x and y columns are required for scatter plot")
        fig = px.scatter(df, x=x_col, y=y_col, **kwargs, title=f"{x_col} vs {y_col}")

    elif chart_type == "bar":
        if not x_col or not y_col:
            raise ValueError("x and y columns are required for bar chart")
        fig = px.bar(df, x=x_col, y=y_col, **kwargs, title=f"{y_col} by {x_col}")

    elif chart_type == "line":
        if not x_col or not y_col:
            raise ValueError("x and y columns are required for line chart")
        fig = px.line(df, x=x_col, y=y_col, **kwargs, title=f"{y_col} over {x_col}")

    elif chart_type == "box":
        if not x_col:
            raise ValueError("x column is required for box plot")
        fig = px.box(df, y=x_col, **kwargs, title=f"Box plot of {x_col}")

    elif chart_type == "pie":
        if not x_col:
            raise ValueError("x (category) column is required for pie chart")
        counts = df[x_col].value_counts().reset_index()
        counts.columns = [x_col, "count"]
        fig = px.pie(counts, names=x_col, values="count", title=f"Distribution of {x_col}")

    elif chart_type == "heatmap":
        num_df = df.select_dtypes(include=[np.number])
        if num_df.shape[1] < 2:
            raise ValueError("At least two numeric columns are required for a heatmap")
        corr = num_df.corr().round(2)
        fig = px.imshow(corr, text_auto=True, title="Correlation Heatmap", aspect="auto")

    else:
        raise ValueError(f"Unsupported chart type: {chart_type}")

    fig.update_layout(template="plotly_white")
    return fig


@app.route("/api/stats")
def api_stats():
    filename = session.get("filename")
    if not filename:
        return jsonify({"error": "No data loaded"}), 400

    try:
        df = load_dataframe(filename)
    except Exception:
        return jsonify({"error": "Could not load data"}), 500

    col = request.args.get("col")
    valid_cols = set(df.columns.tolist())
    if col and col not in valid_cols:
        return jsonify({"error": f"Column '{col}' not found"}), 400

    if col:
        series = df[col]
        if pd.api.types.is_numeric_dtype(series):
            result = {
                "column": col,
                "count": int(series.count()),
                "mean": float(series.mean()),
                "std": float(series.std()),
                "min": float(series.min()),
                "25%": float(series.quantile(0.25)),
                "50%": float(series.median()),
                "75%": float(series.quantile(0.75)),
                "max": float(series.max()),
                "missing": int(series.isnull().sum()),
            }
        else:
            vc = series.value_counts()
            result = {
                "column": col,
                "count": int(series.count()),
                "unique": int(series.nunique()),
                "top": str(vc.index[0]) if not vc.empty else None,
                "top_count": int(vc.iloc[0]) if not vc.empty else 0,
                "missing": int(series.isnull().sum()),
            }
        return jsonify(result)

    # Summary for all columns
    summary = []
    for c in df.columns:
        s = df[c]
        entry = {
            "column": c,
            "dtype": str(s.dtype),
            "missing": int(s.isnull().sum()),
            "unique": int(s.nunique()),
        }
        if pd.api.types.is_numeric_dtype(s):
            entry.update({"mean": round(float(s.mean()), 4), "std": round(float(s.std()), 4)})
        summary.append(entry)

    return jsonify(summary)


if __name__ == "__main__":
    app.run(debug=False)
