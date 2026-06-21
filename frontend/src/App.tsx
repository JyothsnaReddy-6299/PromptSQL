import {BrowserRouter,Routes,Route} from 'react-router-dom'

import LandingPage from './pages/LandingPage.tsx'
import UploadPage from './pages/UploadPage.tsx'
import DashboardPage from "./pages/DashboardPage";

function App(){

return(

<BrowserRouter>

<Routes>

<Route path="/" element={<LandingPage/>}/>

<Route path="/upload" element={<UploadPage/>}/>

<Route path="/dashboard" element={<DashboardPage/>}/>

</Routes>

</BrowserRouter>

)

}

export default App