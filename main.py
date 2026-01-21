from fastapi import FastAPI, Body, Response
from fastapi.responses import JSONResponse
import subprocess, tempfile, os, re
import psutil
import time

app = FastAPI()

MAX_LATEX_SIZE = 5 * 1024 * 1024  # 5mb
MAX_PDF_SIZE = 20 * 1024 * 1024   # 20mb
MAX_MEMORY_MB = 60                # 60MB
def _proc_tree_rss_mb(proc: psutil.Process):
    rss = 0
    procs = [proc]
    try:
        procs += proc.children(recursive=True)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    for p in procs:
        try:
            mi = p.memory_info()
            rss += mi.rss
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return rss / (1024 * 1024)
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
                process = subprocess.Popen(
                    [
                        "pdflatex",
                        "-no-shell-escape",
                        "-interaction=nonstopmode",
                        "-output-directory", temp_dir,
                        tex_path
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )

                ps_process = psutil.Process(process.pid)

                try:
                    while process.poll() is None:
                        try:
                            rss_mb = _proc_tree_rss_mb(ps_process)
                            if rss_mb > MAX_MEMORY_MB:
                                process.kill()
                                process.wait()
                                return JSONResponse(
                                    status_code=507,
                                    content={"status": "failed", "message": f"Memory limit exceeded"}
                                )
                        except psutil.NoSuchProcess:
                            break
                        time.sleep(0.1)

                    stdout, stderr = process.communicate(timeout=30)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                    raise

                result = subprocess.CompletedProcess(
                    process.args, process.returncode, stdout, stderr
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