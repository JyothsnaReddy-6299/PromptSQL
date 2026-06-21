import { Send } from "lucide-react";

export default function ChatBox() {
    return (

        <div className="bg-white rounded-2xl shadow-sm p-6">

            <h2 className="text-xl font-semibold mb-4">
                Chat with Data
            </h2>

            <p className="text-gray-500 mb-6">
                Ask questions about your uploaded dataset.
            </p>


            <textarea
                placeholder="Example: What is the average salary?"
                className="
                    w-full
                    h-32
                    border
                    border-gray-200
                    rounded-xl
                    p-4
                    resize-none
                    focus:outline-none
                    focus:ring-2
                    focus:ring-blue-500
                "
            />


            <div className="flex justify-end mt-4">

                <button
                    className="
                        flex
                        items-center
                        gap-2
                        bg-blue-600
                        text-white
                        px-5
                        py-3
                        rounded-xl
                        hover:bg-blue-700
                        transition
                    "
                >

                    <Send size={18}/>

                    Send

                </button>

            </div>

        </div>

    );
}