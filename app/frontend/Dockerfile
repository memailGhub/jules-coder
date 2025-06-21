# Use an official Nginx runtime as a parent image
FROM nginx:alpine

# Remove default Nginx website
RUN rm -rf /usr/share/nginx/html/*

# Copy static frontend files from the current directory (frontend app root)
# to the Nginx HTML directory
COPY ./index.html /usr/share/nginx/html/index.html
COPY ./style.css /usr/share/nginx/html/style.css
COPY ./script.js /usr/share/nginx/html/script.js

# (Optional) Copy a custom Nginx configuration file if needed.
COPY ./nginx.conf /etc/nginx/conf.d/default.conf

# Make port 80 available to the world outside this container
EXPOSE 80

# Command to run Nginx in the foreground
CMD ["nginx", "-g", "daemon off;"]
