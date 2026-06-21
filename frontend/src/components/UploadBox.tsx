import {useState} from 'react';


export default function UploadBox(){


const[file,setFile]=useState<File|null>(null);

const[status,setStatus]=useState("");



const handleUpload=()=>{


if(!file){

setStatus("Please select a file");

return;

}


console.log(file);


setStatus("Ready for backend");


}





return(


<div>



<input

type="file"


accept=".xlsx,.csv"


onChange={(e)=>{


if(e.target.files){

setFile(e.target.files[0]);

}


}}


/>




<button onClick={handleUpload}>


Upload


</button>




<p>

{status}

</p>


</div>



)



}