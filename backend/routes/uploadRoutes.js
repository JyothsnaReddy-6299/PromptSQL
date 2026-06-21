const express = require("express");
const router = express.Router();
const upload = require("../middleware/upload");

router.post("/file", upload.single("file"), (req, res) => {
  if (!req.file) {
    return res.status(400).json({ message: "No file uploaded" });
  }

  res.json({
    message: "Upload successful",
    file: req.file
  });
});

module.exports = router;