// backend/server.js

try {
  const express = require("express");
  const cors = require("cors");

  const uploadRoutes = require("./routes/uploadRoutes");

  const app = express();

  app.use(cors());
  app.use(express.json());
  app.use("/uploads", express.static("uploads"));
  app.use("/api/upload", uploadRoutes);

  app.listen(5000, () => {
    console.log("Server running on port 5000");
  });

} catch (err) {
  console.error("SERVER FAILED TO START:");
  console.error(err);
}