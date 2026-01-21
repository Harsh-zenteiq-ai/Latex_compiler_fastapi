API to validate and compile Latex codes. 

Packages used : Fastapi,  uvicorn

Texlive is used for the compilation of the latex code 
Texlive-latex-base is enough for simple and small latex code, but texlive-latex-extra and texlive-fonts-recommended is needed to compile latex with complex graphs, links and different fonts. 

Maximum pdf size limit = 20MB
Maximum latex code input size = 5MB
Maximum memory limit = 60MB 
timeout = 30 secs

Input = Latex code 

detects : 
empty inputs 
any trailing contents after the end of the latex code 
syntax errors 
memory limits 
loops 

shell escape disabled to prevent command injection. 
I/O size, memory limits implemented to prevent memory exhaustion