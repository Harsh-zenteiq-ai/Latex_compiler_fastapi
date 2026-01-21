from fastapi import FastAPI, Body, Response
from fastapi.responses import JSONResponse
import subprocess, tempfile, os, re

app = FastAPI()

MAX_LATEX_SIZE = 5 * 1024 * 1024 #5mb
MAX_PDF_SIZE = 20 * 1024 * 1024  #20mb

@app.post("/compile")
async def compile_latex(code: str = Body(media_type="text/plain")):

    if not code or not code.strip():
        return JSONResponse(
            status_code=400,
            content={"status": "failed", "message": "Empty LaTeX code"}
        )

    if len(code) > MAX_LATEX_SIZE:
        return JSONResponse(
            status_code=413,
            content={"status": "failed", "message": "LaTeX input too large"}
        )

    if not re.search(r"\\end\{document\}\s*$", code, re.DOTALL):
        return JSONResponse(
            status_code=400,
            content={"status": "failed", "message": "invalid or trailing content after \\end{document}"}
        )
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            tex_path = os.path.join(temp_dir, "document.tex")

            with open(tex_path, "w") as f:
                f.write(code)

            for _ in range(2):
                result = subprocess.run(
                    [
                        "pdflatex",
                        "-no-shell-escape",
                        "-interaction=nonstopmode",
                        "-output-directory", temp_dir,
                        tex_path
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if result.returncode != 0:
                    break

            pdf_path = os.path.join(temp_dir, "document.pdf")

            if result.returncode == 0 and os.path.exists(pdf_path):
                if os.path.getsize(pdf_path) > MAX_PDF_SIZE:
                    return JSONResponse(
                        status_code=507,
                        content={"status": "failed", "message": "PDF too large"}
                    )

                with open(pdf_path, "rb") as pdf_file:
                    pdf_bytes = pdf_file.read()
                return Response(
                    content=pdf_bytes,
                    media_type="application/pdf",
                    headers={"Content-Disposition": "attachment; filename=document.pdf"}
                )
            log = result.stdout + "\n" + result.stderr
            errors = [
                line for line in log.splitlines()
                if line.startswith("!") or "Error" in line
            ]
            return JSONResponse(
                status_code=400,
                content={
                    "status": "failed",
                    "message": "LaTeX compilation failed",
                    "errors": errors[:10] or ["Unknown LaTeX error"]
                }
            )
    except subprocess.TimeoutExpired:
        return JSONResponse(
            status_code=408,
            content={"status": "failed", "message": "Compilation timed out"}
        )
