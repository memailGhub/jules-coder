# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app/backend

# Copy the requirements file into the container at /app/backend
COPY ./requirements.txt /app/backend/requirements.txt

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the backend application code into the container at /app/backend
COPY . /app/backend/

# Make port 8000 available to the world outside this container
EXPOSE 8000

# Command to run the application using Uvicorn
CMD ["uvicorn", "app.backend.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
