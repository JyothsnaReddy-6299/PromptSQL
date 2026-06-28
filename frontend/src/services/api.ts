const API_URL = "http://127.0.0.1:8000";

export async function getHealth() {
  const response = await fetch(`${API_URL}/health`);
  return response.json();
}

// ✅ ADD THIS FUNCTION
export async function askQuestion(question: string, table_name: string) {
  const response = await fetch(`${API_URL}/ask`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      question,
      table_name,
    }),
  });

  return response.json();
}