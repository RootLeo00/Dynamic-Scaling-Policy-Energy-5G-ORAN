FROM ubuntu:22.04 as base

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt requirements.txt

# Install the dependencies
RUN apt update
RUN apt install -y python3 python3-pip
RUN pip3 install --no-cache-dir -r requirements.txt
RUN apt install -y gpg curl
RUN curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.30/deb/Release.key | gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg
RUN echo "deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.30/deb/ /" | tee /etc/apt/sources.list.d/kubernetes.list
RUN apt update
RUN apt install -y kubectl

# Copy the Flask app code into the container
COPY . .
RUN cp -r /app/kube_conf /root/.kube
# Expose the port the app runs on
EXPOSE 5000

# Command to run the app
CMD ["python3", "app.py"]
