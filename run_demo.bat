@echo off
REM ==============================================================================
REM Rakshapath - Windows Local Demo Launcher
REM ==============================================================================

echo ====================================================================
echo Starting Rakshapath Multi-Hazard Emergency Routing Dashboard...
echo Study Area: Daraganj, Prayagraj, India
echo ====================================================================

IF EXIST .venv\Scripts\streamlit.exe (
    .\.venv\Scripts\streamlit.exe run app.py --server.port=8501
) ELSE IF EXIST .venv\Scripts\python.exe (
    .\.venv\Scripts\python.exe -m streamlit run app.py --server.port=8501
) ELSE (
    streamlit run app.py --server.port=8501
)

pause
