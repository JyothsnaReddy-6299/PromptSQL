import { useNavigate } from "react-router-dom";

export default function CTA(){
    const navigate = useNavigate();


return(


<section className="bg-gradient-to-b from-cyan-50 to-white py-28">



<div className="max-w-7xl mx-auto">


<div className="bg-gradient-to-r from-blue-600 to-cyan-500 rounded-[40px] py-24 px-12 text-center">



<h2 className="text-6xl font-bold text-white">


Ready to unlock your data insights?


</h2>



<p className="mt-6 text-2xl text-blue-100">


Join thousands of analysts using AI to make better decisions


</p>




<button

onClick={()=>navigate("/upload")}

className="mt-12 bg-white text-blue-600 px-12 py-5 rounded-2xl font-semibold text-xl hover:scale-105 transition "

>

Get Started Free

</button>



</div>


</div>


</section>



)


}