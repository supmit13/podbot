#!/bin/bash

cd /home/supmit/work/hitcountbot/web/hitweb
/etc/init.d/nginx restart
nohup uwsgi --ini uwsgi.ini &
/etc/init.d/redis-server restart
nohup python -m celery -A hitweb worker -l debug &
echo "All services and applications started successfully"

