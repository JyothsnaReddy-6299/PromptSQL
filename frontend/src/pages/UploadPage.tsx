import { ArrowLeft, Upload, FileSpreadsheet, CheckCircle, Brain } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useState } from "react";
import axios from "axios";

export default function UploadPage() {

    const navigate = useNavigate();

    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const [uploading, setUploading] = useState(false);
    const [uploadStatus, setUploadStatus] = useState("");
    const [progress, setProgress] = useState(0);

    const handleUpload = async () => {

        if (!selectedFile) {
            setUploadStatus("Please select a file");
            return;
        }

        try {

            setUploading(true);
            setProgress(30);

            const formData = new FormData();
            formData.append("file", selectedFile);

            const response = await axios.post(
                "http://127.0.0.1:8000/upload",
                formData,
                {
                    headers: {
                        "Content-Type": "multipart/form-data"
                    }
                }
            );

            console.log(response.data);

            setProgress(100);
            setUploading(false);
            setUploadStatus("Upload successful");

            // FIX: stable persistence for dashboard reload safety
            sessionStorage.setItem(
                "dataset",
                JSON.stringify(response.data)
            );

            // FIX: safer navigation (no reliance on React state)
            navigate("/dashboard");

        } catch (error) {

            console.log(error);
            setUploading(false);
            setUploadStatus("Upload failed");
        }
    };

    return (

        <div className="relative min-h-screen overflow-hidden bg-gradient-to-b from-blue-50 via-white to-white">

            <div className="absolute top-0 left-0 w-96 h-96 bg-blue-200 rounded-full blur-3xl opacity-40"/>
            <div className="absolute top-0 right-0 w-96 h-96 bg-cyan-200 rounded-full blur-3xl opacity-40"/>

            <div className="relative z-10 max-w-5xl mx-auto p-10">

                <button
                    onClick={() => navigate("/")}
                    className="flex gap-2 items-center mb-10 text-blue-600"
                >
                    <ArrowLeft size={18}/>
                    Back
                </button>

                <h1 className="text-5xl font-bold mb-3">
                    Upload Dataset
                </h1>

                <p className="text-gray-500 mb-12">
                    Upload your Excel or CSV file to start AI analysis
                </p>

                <div className="bg-white rounded-3xl p-10 border shadow-sm">

                    <div className="border-2 border-dashed border-blue-300 rounded-3xl p-10 text-center">

                        <div className="bg-blue-100 w-16 h-16 rounded-full flex items-center justify-center mx-auto">
                            <Upload size={26} className="text-blue-600"/>
                        </div>

                        <h2 className="mt-5 text-2xl font-semibold">
                            Drag & Drop Files
                        </h2>

                        <p className="mt-2 text-gray-500">
                            or click below to browse
                        </p>

                        <input
                            id="fileUpload"
                            hidden
                            type="file"
                            accept=".csv,.xlsx,.xls"
                            onChange={(e) => {
                                if (e.target.files) {
                                    setSelectedFile(e.target.files[0]);
                                }
                            }}
                        />

                        <div className="mt-8 flex justify-center gap-4">

                            <label
                                htmlFor="fileUpload"
                                className="cursor-pointer bg-gradient-to-r from-blue-600 to-cyan-500 text-white px-6 py-3 rounded-xl"
                            >
                                Browse Files
                            </label>

                            <button
                                onClick={handleUpload}
                                className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-xl"
                            >
                                {uploading ? "Uploading..." : "Upload"}
                            </button>

                        </div>

                        {selectedFile && (
                            <div className="mt-5 inline-block bg-blue-50 px-4 py-2 rounded-xl">
                                <p className="text-blue-700 text-sm">
                                    📄 {selectedFile.name}
                                </p>
                            </div>
                        )}

                        {uploading && (
                            <div className="mt-6">
                                <div className="bg-gray-200 rounded-full h-3">
                                    <div
                                        style={{ width: `${progress}%` }}
                                        className="bg-blue-600 h-3 rounded-full transition-all"
                                    />
                                </div>
                            </div>
                        )}

                        {uploadStatus && (
                            <p className="mt-5 text-green-600">
                                {uploadStatus}
                            </p>
                        )}

                        <p className="mt-6 text-sm text-gray-400">
                            Supported: CSV • XLS • XLSX
                        </p>

                    </div>
                </div>

            </div>
        </div>
    );
}