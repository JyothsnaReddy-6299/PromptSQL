import { FileSpreadsheet, CheckCircle, Brain } from "lucide-react";

export default function UploadFeatures(){

const features=[

{
icon:<FileSpreadsheet className="text-blue-600"/>,
title:"Multiple Formats",
desc:"CSV, XLS, XLSX"
},

{
icon:<CheckCircle className="text-green-600"/>,
title:"Validation",
desc:"Instant file checking"
},

{
icon:<Brain className="text-purple-600"/>,
title:"AI Ready",
desc:"Prepared for analysis"
}

]


return(

<div className="grid md:grid-cols-3 gap-6 mt-12">

{

features.map((feature,index)=>(

<div
key={index}
className="bg-white rounded-3xl p-6 border shadow-sm hover:shadow-lg transition"
>


<div className="mb-4">

{feature.icon}

</div>


<h3 className="font-semibold">

{feature.title}

</h3>


<p className="text-gray-500 mt-2">

{feature.desc}

</p>

</div>

))

}


</div>

)

}