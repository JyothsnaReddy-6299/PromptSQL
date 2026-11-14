FROM node:18-alpine

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

EXPOSE 5173

HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=5 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:5173/ || exit 1

# Expose host to allow connection from outer browser loop
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
