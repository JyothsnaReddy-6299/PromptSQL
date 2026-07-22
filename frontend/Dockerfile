FROM node:18-alpine

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

EXPOSE 5173

# Expose host to allow connection from outer browser loop
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
