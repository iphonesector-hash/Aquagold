import os

from werkzeug.security import generate_password_hash

import app_v3

username = os.environ["AQUAGOLD_ADMIN_USERNAME"]
password = os.environ["AQUAGOLD_ADMIN_PASSWORD"]

with app_v3.get_db() as db, db.cursor() as cur:
    cur.execute(
        """
        insert into users(username,password_hash,first_name,last_name,role,active)
        values(%s,%s,'Smoke','Admin','superadmin',true)
        on conflict(username) do update set
          password_hash=excluded.password_hash,
          role='superadmin',
          active=true
        """,
        (username, generate_password_hash(password)),
    )
