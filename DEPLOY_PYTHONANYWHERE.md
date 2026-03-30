# PythonAnywhere Deployment

This project now includes a WSGI entry point in `pythonanywhere_wsgi.py`, so you can deploy the same site to PythonAnywhere.

## 1. Upload your project

Put the whole `Website` folder in your PythonAnywhere home directory.

Example target path:

```text
/home/YOUR_USERNAME/Website
```

## 2. Create a web app

In PythonAnywhere:

1. Open the **Web** tab.
2. Choose **Add a new web app**.
3. Pick your free `pythonanywhere.com` domain.
4. Choose **Manual configuration**.
5. Pick **Python 3.13** or the newest Python 3 version they offer.

## 3. Point the WSGI file at this project

Open the WSGI configuration file PythonAnywhere creates, then replace its contents with:

```python
import sys
from pathlib import Path

project_dir = Path("/home/YOUR_USERNAME/Website")
if str(project_dir) not in sys.path:
    sys.path.insert(0, str(project_dir))

from server import application
```

## 4. Set up static files

In the **Web** tab, add this static mapping:

- URL: `/static/`
- Directory: `/home/YOUR_USERNAME/Website/static/`

## 5. Reload the site

Press **Reload** in the **Web** tab.

Your public site will then be available at:

```text
https://YOUR_USERNAME.pythonanywhere.com
```

## Notes

- Your posts are stored in `thoughts.db` inside the project folder.
- The first time you open the public site and click `Owner Access`, create your password there.
- Friends can view the site, but only someone with your password can edit.
