import { ArrowLeft, Upload, FileSpreadsheet, CheckCircle, Brain } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useState } from "react";

export default function UploadPage() {

    const navigate = useNavigate();

    const [selectedFile, setSelectedFile] = useState<File | null>(null);

    const [uploading, setUploading] = useState(false);

    const [uploadStatus, setUploadStatus] = useState("");

    const [progress, setProgress] = useState(0);



    const handleUpload = () => {

        if (!selectedFile) {

            setUploadStatus("Please select a file");
            return;
        }

        setUploading(true);

        setProgress(0);

        let value = 0;


        const timer = setInterval(() => {

            value += 20;

            setProgress(value);


            if (value >= 100) {

                clearInterval(timer);

                setUploading(false);

                setUploadStatus("Ready for AI Analysis");

                console.log(selectedFile);

            }

        }, 300);


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




                {/* Upload Card */}

                <div className="bg-white rounded-3xl p-10 border shadow-sm">



                    <div className="border-2 border-dashed border-blue-300 rounded-3xl p-10 text-center">



                        <div className="bg-blue-100 w-16 h-16 rounded-full flex items-center justify-center mx-auto">

                            <Upload

                                size={26}

                                className="text-blue-600"

                            />

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

                                    setSelectedFile(

                                        e.target.files[0]

                                    );

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


                                        style={{

                                            width: `${progress}%`

                                        }}

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




                        {uploadStatus && (


                            <button


                                onClick={() => navigate("/dashboard")}


                                className="mt-6 bg-green-600 hover:bg-green-700 text-white px-6 py-3 rounded-xl"


                            >

                                Continue to Dashboard


                            </button>


                        )}




                        <p className="mt-6 text-sm text-gray-400">


                            Supported: CSV • XLS • XLSX


                        </p>



                    </div>


                </div>




                {/* Features Section */}


                <div className="grid md:grid-cols-3 gap-6 mt-10">



                    <div className="bg-white rounded-3xl p-6 border border-slate-200 shadow-lg hover:shadow-xl transition-all duration-300 bg-gradient-to-br from-white to-blue-50/30">

                        <FileSpreadsheet className="text-blue-600"/>

                        <h3 className="mt-4 font-semibold">

                            Multiple Formats

                        </h3>

                        <p className="text-gray-500 mt-2">

                            CSV, XLS, XLSX

                        </p>

                    </div>



                    <div className="bg-white rounded-3xl p-6 border border-slate-200 shadow-lg hover:shadow-xl transition-all duration-300 bg-gradient-to-br from-white to-blue-50/30">

                        <CheckCircle className="text-green-600"/>

                        <h3 className="mt-4 font-semibold">

                            Validation

                        </h3>

                        <p className="text-gray-500 mt-2">

                            Instant file checking

                        </p>

                    </div>



                    <div className="bg-white rounded-3xl p-6 border border-slate-200 shadow-lg hover:shadow-xl transition-all duration-300 bg-gradient-to-br from-white to-blue-50/30">

                        <Brain className="text-purple-600"/>

                        <h3 className="mt-4 font-semibold">

                            AI Ready

                        </h3>

                        <p className="text-gray-500 mt-2">

                            Prepared for analysis

                        </p>

                    </div>



                </div>



            </div>


        </div>

    );

}