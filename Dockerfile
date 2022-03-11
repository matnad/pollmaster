FROM python:3.7

WORKDIR /usr/src/

RUN pip install --upgrade pip

COPY docker-requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

VOLUME [ "/usr/src/app" ]
WORKDIR /usr/src/app/

#ENTRYPOINT [ "python", "/usr/src/app/pollmaster.py" ]
ENTRYPOINT [ "python", "/usr/src/app/launcher.py" ]

