from fastapi import FastAPI, Body, Response
from fastapi.responses import JSONResponse
import subprocess, tempfile, os, re
import psutil
import time

app = FastAPI()

MAX_LATEX_SIZE = 5 * 1024 * 1024  
MAX_PDF_SIZE = 20 * 1024 * 1024   
MAX_MEMORY_MB = 60              
TIMEOUT_SECONDS = 30  

def _proc_tree_rss_mb(proc: psutil.Process):
    rss = 0
    try:
        procs = [proc] + proc.children(recursive=True)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return 0
    for p in procs:
        try:
            mi = p.memory_info()
            rss += mi.rss
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return rss / (1024 * 1024)

@app.post("/compile")
def compile_latex(code: str = Body(media_type="text/plain")):

    if not code or not code.strip():
        return JSONResponse(status_code=400, content={"status": "failed", "message": "Empty LaTeX code"})

    if len(code) > MAX_LATEX_SIZE:
        return JSONResponse(status_code=413, content={"status": "failed", "message": "LaTeX input too large"})

    if not re.search(r"\\end\{document\}\s*$", code, re.DOTALL):
        return JSONResponse(
            status_code=400,
            content={"status": "failed", "message": "invalid or trailing content after \\end{document}"}
        )

    with tempfile.TemporaryDirectory() as temp_dir:
        tex_path = os.path.join(temp_dir, "document.tex")
        log_path = os.path.join(temp_dir, "document.log") 
        
        with open(tex_path, "w") as f:
            f.write(code)

        for _ in range(2):
            # Using file for stdout to prevent deadlock
            with open(log_path, "w") as log_file:
                process = subprocess.Popen(
                    [
                        "pdflatex",
                        "-no-shell-escape",
                        "-interaction=nonstopmode",
                        "-output-directory", temp_dir,
                        tex_path
                    ],
                    stdout=log_file,        
                    stderr=subprocess.STDOUT, 
                    cwd=temp_dir
                )

                ps_process = psutil.Process(process.pid)
                start_time = time.time()

                while process.poll() is None:
                    # Manual Timeout Check
                    if time.time() - start_time > TIMEOUT_SECONDS:
                        process.kill()
                        return JSONResponse(
                            status_code=408,
                            content={"status": "failed", "message": "Compilation timed out"}
                        )

                    # Memory Check
                    try:
                        rss_mb = _proc_tree_rss_mb(ps_process)
                        if rss_mb > MAX_MEMORY_MB:
                            process.kill()
                            return JSONResponse(
                                status_code=507,
                                content={"status": "failed", "message": "Memory limit exceeded"}
                            )
                    except psutil.NoSuchProcess:
                        break
                    
                    time.sleep(0.1)

                if process.returncode != 0:
                    break

        pdf_path = os.path.join(temp_dir, "document.pdf")

        if process.returncode == 0 and os.path.exists(pdf_path):
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

        errors = []
        if os.path.exists(log_path):
            with open(log_path, "r", errors="replace") as f:
                log_content = f.read()
                errors = [
                    line for line in log_content.splitlines()
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