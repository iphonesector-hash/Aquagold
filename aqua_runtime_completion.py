"""Final scoped UI corrections for the finance-map test branch."""
from flask import request
import app_v3

@app_v3.app.get('/aqua-runtime-completion.css')
def aqua_runtime_completion_css():
    return app_v3.send_from_directory('.', 'aqua-runtime-completion.css',mimetype='text/css',max_age=0)

@app_v3.app.after_request
def inject_aqua_runtime_completion(response):
    if request.path in {'/','/index.html'} and response.mimetype=='text/html':
        response.direct_passthrough=False;body=response.get_data(as_text=True)
        if '/aqua-runtime-completion.css' not in body:
            body=body.replace('</head>','<link rel="stylesheet" href="/aqua-runtime-completion.css?v=20260914-1"></head>',1)
            response.set_data(body);response.headers['Content-Length']=str(len(response.get_data()));response.headers['Cache-Control']='no-store, max-age=0'
    return response
