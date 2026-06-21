import { Upload, Sparkles } from "lucide-react";
import { useNavigate } from "react-router-dom";

export default function Hero() {



const navigate = useNavigate();

const handleUploadClick = () => {
    navigate("/upload");
};



return (

<section className="pt-36 text-center py-24">


<div className="inline-flex items-center gap-2 bg-blue-100 px-5 py-2 rounded-full text-blue-600">

<Sparkles size={16}/>

Powered by Advanced AI Technology

</div>



<h1 className="mt-10 text-7xl font-bold leading-tight">


AI Data Analytics


<br/>


Assistant



</h1>



<p className="mt-8 text-gray-500 text-xl max-w-2xl mx-auto">


Analyze Excel and CSV files using natural language.


Generate charts, insights and reports instantly.



</p>




<button
    onClick={handleUploadClick}
    className="mt-12 bg-gradient-to-r from-blue-600 to-cyan-500 px-8 py-4 rounded-xl text-white flex gap-3 items-center mx-auto hover:scale-105 transition"
>
    Upload Dataset
</button>



</section>



);

}