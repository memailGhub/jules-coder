# Quantitative Intraday Options Trading Analysis Tool

This project aims to build a modular, production-grade web application for quantitative intraday options trading analysis, implementing Nitin Murarka's Delta + ATR-based strike selection strategy.

## Frontend (Plain HTML/CSS/JS)

The frontend is a simple HTML, CSS, and JavaScript application located in the \`app/frontend\` directory.

### Running the Frontend

1.  **Ensure the Backend is Running:**
    The backend FastAPI server must be running (typically on \`http://localhost:8000\`). Refer to the backend setup instructions if not already running. The \`script.js\` file in the frontend is configured to connect to this address.

2.  **Serving the Frontend Files:**
    Since the frontend makes API calls (\`fetch\`) to a backend that might be on a different port (e.g., backend on 8000, frontend served directly from filesystem or another simple server on a different port), you might encounter Cross-Origin Resource Sharing (CORS) issues if you simply open \`index.html\` directly in the browser from the file system (i.e., \`file://...\` URL).

    To avoid CORS issues:
    *   **Backend CORS Configuration:** The FastAPI backend (`app/backend/api/main.py`) should be configured to allow requests from the origin the frontend is served from. If you are serving the frontend locally for development (e.g. using a simple HTTP server), you might need to add that origin (e.g., \`http://localhost:8080\`, \`http://127.0.0.1:8080\`) to the backend's CORS allowed origins.
        *Example FastAPI CORS setup (add to \`main.py\`):*
        \`\`\`python
        from fastapi.middleware.cors import CORSMiddleware

        # ... (other imports)

        app = FastAPI(...) # Your app instance

        origins = [
            "http://localhost", # Origin if serving from file system (often null, but some browsers might map to this)
            "http://localhost:8080", # Example if using python -m http.server on port 8080
            "http://127.0.0.1:8080", # Also common for local http server
            # Add other origins as needed
        ]

        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"], # Allows all methods
            allow_headers=["*"], # Allows all headers
        )
        \`\`\`
        *(Note: The above CORS snippet is an example; the actual backend code was not modified in this subtask. This is informational for the user.)*

    *   **Using a Simple HTTP Server:** The easiest way to serve the frontend files from a proper \`http://\` origin is to use a simple local HTTP server.
        Navigate to the \`app/frontend\` directory in your terminal and run:
        \`\`\`bash
        python -m http.server 8080
        \`\`\`
        (If you have Python 2, the command is \`python -m SimpleHTTPServer 8080\`).
        Then, open your browser and go to \`http://localhost:8080\` or \`http://127.0.0.1:8080\`.

3.  **Interacting with the Dashboard:**
    *   Select an index (NIFTY, BANKNIFTY, TEST_NIFTY) and click "Fetch Market Data" to see live market details.
    *   Fill in the "Strategy Recommendation" form and click "Get Recommendation" to see trading suggestions based on your inputs and the backend logic.

### Files
*   \`app/frontend/index.html\`: The main HTML file.
*   \`app/frontend/style.css\`: CSS styles for the page.
*   \`app/frontend/script.js\`: JavaScript for API calls and dynamic UI updates.


## Dockerization

This application can be built and run using Docker and Docker Compose.
Dockerfiles are provided for both the backend and frontend services, and a \`docker-compose.yml\` file orchestrates the deployment.

### Prerequisites

*   Docker installed and running.
*   Docker Compose installed (usually comes with Docker Desktop).

### Building and Running with Docker Compose

1.  **Navigate to the Project Root:**
    Open your terminal and navigate to the root directory of this project (the directory containing the \`docker-compose.yml\` file).

2.  **Build the Docker Images:**
    Run the following command to build the images for the backend and frontend services as defined in their respective Dockerfiles:
    \`\`\`bash
    docker-compose build
    \`\`\`

3.  **Start the Services:**
    Once the images are built, start the services in detached mode (runs in the background):
    \`\`\`bash
    docker-compose up -d
    \`\`\`
    If you want to see the logs directly in your terminal (attached mode), you can run:
    \`\`\`bash
    docker-compose up
    \`\`\`
    (Use Ctrl+C to stop if running in attached mode).

4.  **Accessing the Services:**
    *   **Frontend:** Open your web browser and go to \`http://localhost:8080\`. The frontend application (served by Nginx) should be accessible here. API calls from the frontend are configured to be proxied to the backend by Nginx.
    *   **Backend API Docs:** The backend FastAPI application's interactive documentation (Swagger UI) can be accessed at \`http://localhost:8000/docs\`.
    *   **Backend API Base URL (if accessing directly):** \`http://localhost:8000\`

5.  **Database Persistence:**
    The SQLite database (\`trading_analysis.db\`) used by the backend is configured to be stored in the project root directory on your host machine. This is achieved via a volume mount defined in \`docker-compose.yml\`. This means your database will persist even if the Docker containers are stopped and removed.

6.  **Stopping the Services:**
    To stop the running services (if running in detached mode or from another terminal):
    \`\`\`bash
    docker-compose down
    \`\`\`
    This will stop and remove the containers. If you want to remove the volumes as well (warning: this will delete data like your SQLite database if it's managed by Docker Compose volumes explicitly, though here it's a bind mount so the file remains), you can use:
    \`\`\`bash
    docker-compose down -v
    \`\`\`

### Dockerfile Details

*   **Backend (`app/backend/Dockerfile`):** Builds a Python container using \`python:3.9-slim\`, installs dependencies from \`requirements.txt\`, and runs the FastAPI application using Uvicorn. The SQLite database file is expected at \`/app/backend/trading_analysis.db\` within the container, which is mapped to \`./trading_analysis.db\` in the project root on the host.
*   **Frontend (`app/frontend/Dockerfile`):** Builds an Nginx container using \`nginx:alpine\`, serves the static HTML, CSS, and JS files from \`app/frontend\`. It includes an Nginx configuration (\`nginx.conf\`) that also proxies API requests starting with \`/api/\` to the backend service (\`http://backend:8000\`).
