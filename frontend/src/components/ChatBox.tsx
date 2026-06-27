import { useState } from "react";
import axios from "axios";

export default function ChatBox() {

const [question,setQuestion]=useState("");

const [summary,setSummary]=useState("");
const [sql,setSql]=useState("");
const [records,setRecords]=useState<any[]>([]);

const askAI = async()=>{

try{

const response = await axios.post(

"http://127.0.0.1:8000/ask",

{

question,

table_name:"data"

}

);

setSummary(response.data.summary);

setSql(response.data.sql);

setRecords(response.data.result);

}

catch(error){

console.log(error);

}

};

return(

<div className="bg-white p-6 rounded-3xl shadow">

<h2 className="text-xl font-bold mb-4">

Ask AI

</h2>


<textarea

value={question}

onChange={(e)=>setQuestion(e.target.value)}

placeholder="Ask anything about your dataset..."

className="w-full border rounded-xl p-3 h-32"

/>


<button onClick={askAI} className="mt-4 bg-blue-600 text-white px-5 py-2 rounded-xl">

Ask

</button>



<div className="mt-6">

    <h3 className="font-semibold text-lg">
        AI Response
    </h3>

    <p className="bg-slate-100 p-4 rounded-xl mt-2">
        {summary}
    </p>

</div>


<div className="mt-6">

    <h3 className="font-semibold">
        Generated SQL
    </h3>

    <div className="bg-slate-100 p-4 rounded-xl mt-2">
        <code>
            {sql}
        </code>
    </div>

</div>

</div>

);

}