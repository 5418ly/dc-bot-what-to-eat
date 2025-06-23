# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
# --no-cache-dir reduces image size
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application's code into the container at /app
COPY . .

# Make port 80 available to the world outside this container (if your bot needs it, usually not for discord.py)
# EXPOSE 80 

# Define environment variables (these can be overridden at runtime)

# Ensures Python output is sent straight to terminal (Docker logs)
ENV PYTHONUNBUFFERED=1 
# ENV DISCORD_BOT_TOKEN="your_discord_token_here" # Set these during `docker run` or in docker-compose
# ENV OPENAI_API_KEY="your_openai_key_here"
# ENV OPENAI_MODEL_ID="gpt-3.5-turbo"
# ENV MAX_HISTORY_MESSAGES="10"
# ENV MAX_OUTPUT_TOKENS="500"
# ENV SYSTEM_MESSAGE_CONTENT="You are a helpful AI assistant."
# ENV OPENAI_API_BASE_URL="" # Optional: e.g. "http://localhost:1234/v1" for local LLMs

# Run bot.py when the container launches
CMD ["python", "bot.py"]