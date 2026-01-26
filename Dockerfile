FROM python:3.10.18-slim

# Install git for cloning/updating the repository
RUN apt-get update && \
    apt-get install -y git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Clone the repository (this will happen at build time)
RUN git clone https://github.com/sr-lab/ProfOlaf.git .
RUN git pull origin main

# Install Python dependencies with increased timeout for large packages
# The timeout is set high (5000 seconds) to handle large CUDA packages like nvidia-cudnn-cu12 (571 MB)
# Using retry logic in case of network timeouts
RUN pip install --default-timeout=5000 --no-cache-dir -r requirements.txt || \
    (echo "First attempt failed, retrying with longer timeout..." && \
     sleep 5 && \
     pip install --default-timeout=10000 --no-cache-dir -r requirements.txt)
# Create a startup script that allows users to choose how to run the tool
RUN echo '#!/bin/bash\n\
echo "===================================="\n\
echo "     Welcome to ProfOlaf"\n\
echo "===================================="\n\
echo ""\n\
echo "Updating repository..."\n\
git pull origin main\n\
echo ""\n\
echo "How would you like to run ProfOlaf?"\n\
echo "  1) Web Application (accessible at http://localhost:5000)"\n\
echo "  2) CLI Scripts (interactive shell)"\n\
echo ""\n\
read -p "Enter your choice (1-2): " choice\n\
echo ""\n\
case $choice in\n\
  1)\n\
    echo "Starting web application..."\n\
    python app.py\n\
    ;;\n\
  2)\n\
    echo "Starting interactive shell..."\n\
    echo "Available scripts:"\n\
    ls -1 *.py | grep "^[0-9]" | sort\n\
    echo ""\n\
    echo "Run scripts with: python <script_name.py> [arguments]"\n\
    echo "For help on any script, use: python <script_name.py> --help"\n\
    /bin/bash\n\
    ;;\n\
  *)\n\
    echo "Invalid choice. Starting interactive shell..."\n\
    /bin/bash\n\
    ;;\n\
esac\n\
' > /app/entrypoint.sh && chmod +x /app/entrypoint.sh

# Expose port for the web application
EXPOSE 5000

# Set the entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]