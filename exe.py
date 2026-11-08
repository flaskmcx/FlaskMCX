import subprocess as s

s.run([r'C:\Users\Administrator\Desktop\FlaskMCX\.venv\Scripts\pyinstaller.exe','--add-data','data;data','--add-data','static;static','--icon=static\\icon.ico','main.py'])