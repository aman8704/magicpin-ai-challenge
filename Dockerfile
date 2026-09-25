FROM python:3.12-slim
WORKDIR /app
COPY bot.py ./
EXPOSE 8080
CMD ["python3", "bot.py"]
