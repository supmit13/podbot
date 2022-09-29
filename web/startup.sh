#!/bin/bash

cd /home/supmit/work/hitcountbot/web/hitweb
/etc/init.d/nginx start
nohup uwsgi --ini hitweb_uwsgi.ini &
/etc/init.d/redis-server &
nohup python -m celery -A hitweb worker -l debug &
echo "All services and applications started successfully"

