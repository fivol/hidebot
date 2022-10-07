FROM python:3.9
WORKDIR /app
COPY Pipfile .
COPY Pipfile.lock .
RUN pip install pipenv && pipenv install --dev --system --deploy
COPY . .


CMD python main.py