# Use official Python image as base
FROM python:3.10-slim  

# Set the working directory inside the container
WORKDIR /app/xliff_file_app 
COPY . .
# Copy requirements file and install dependencies
COPY requirements.txt .  
RUN pip install --no-cache-dir -r requirements.txt  

# Copy the entire project into the container
COPY . .  

# Expose the port Django runs on (default: 8000)
EXPOSE 8000  

# Command to run the Django server
CMD ["python", "application/manage.py", "runserver", "0.0.0.0:8000"]
