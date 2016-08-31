FROM 347907137948.dkr.ecr.us-east-1.amazonaws.com/python:3.4.3

RUN apt-get update &&\
    apt-get install -y -q sqlite3 &&\
    rm -rf /var/lib/apt/lists/*

ENV USE_ENV true
ENV WORKDIR /opt/services/hello-world-python
ENV HOME $WORKDIR

RUN groupadd app &&\
    useradd -g app -d $WORKDIR -s /sbin/nologin -c 'Docker image user for the app' app &&\
    mkdir -p $WORKDIR

ADD . /opt/services/hello-world-python

RUN pip install -r $WORKDIR/requirements.txt

RUN chown -R app:app $WORKDIR

USER app

CMD cd $WORKDIR && python ./app.py

