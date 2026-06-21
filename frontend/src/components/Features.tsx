
import{

Brain,

BarChart3,

Sparkles,

FileText

}

from "lucide-react"



const cards=[


{

title:"Natural Language Queries",

icon:<Brain/>,

desc:"Ask questions in plain English"

},


{

title:"Automated Insights",

icon:<Sparkles/>,

desc:"Discover trends instantly"

},

{

title:"Interactive Dashboards",

icon:<BarChart3/>,

desc:"Visualize your datasets"

},

{

title:"AI Reports",

icon:<FileText/>,

desc:"Generate reports"

}


]



export default function Features(){


return(

<section className="py-24 bg-gradient-to-b from-white via-blue-50 to-cyan-50">


<h2 className="text-center text-4xl font-bold">

Powerful Features


</h2>


<div className="max-w-6xl mx-auto grid md:grid-cols-2 gap-8 mt-16">


{


cards.map((card)=>(


<div className="bg-white border rounded-3xl p-8 shadow-sm hover:shadow-xl transition duration-300">


<div className="bg-blue-100 w-12 h-12 rounded-xl flex items-center justify-center text-blue-600">


{card.icon}


</div>


<p className="mt-3 text-gray-500">


{card.desc}


</p>

<p>

{card.desc}

</p>



</div>


))


}



</div>


</section>


)


}


