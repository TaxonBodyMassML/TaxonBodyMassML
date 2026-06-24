// handles js functionality and API request for question permanence

const questionBar = document.getElementById('question-bar');
const submitQuestion = document.getElementById('submit-question');
const questionsContent = document.getElementById('questions-content');

const API_BASE = "https://haileystaxonbodymassml.onrender.com";

async function loadQuestions() {
    try {
        const res = await fetch(`${API_BASE}/questions`);

        if (!res.ok) {
            throw new Error(`Server error: ${res.status}`);
        }

        const questions = await res.json();

        questionsContent.innerHTML = "";

        if (questions.length === 0) {
            const emptyMsg = document.createElement("p");
            emptyMsg.textContent = "No questions submitted yet.";
            emptyMsg.classList.add("no-questions");
            questionsContent.appendChild(emptyMsg);
            return;
        }

        questions.forEach(record => {
            const p = document.createElement("p");
            p.classList.add("user-question");
            p.textContent = record.text;

            if (record.status === "unanswered") {
                const statusLabel = document.createElement("span");
                statusLabel.classList.add("unanswered");
                statusLabel.textContent = " - (unanswered)";
                p.appendChild(statusLabel);
            }

            questionsContent.appendChild(p);
        });

    } catch (error) {
        console.error("Failed to load questions:", error);

        questionsContent.innerHTML = "";
        const errorMsg = document.createElement("p");
        errorMsg.textContent = "Unable to load questions. Please try again later.";
        errorMsg.classList.add("error-message");
        questionsContent.appendChild(errorMsg);
    }
}

async function saveQuestion(text) {
    try {
        const res = await fetch(`${API_BASE}/questions`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ text })
        });

        if (!res.ok) {
            throw new Error(`Server error: ${res.status}`);
        }

        return true;

    } catch (error) {
        console.error("Failed to save question:", error);
        alert("Could not submit question. Please try again.");
        return false;
    }
}

submitQuestion.addEventListener("click", async () => {
    const text = questionBar.value.trim();

    if (text === "") return;

    const success = await saveQuestion(text);

    if (success) {
        questionBar.value = "";
        await loadQuestions();
    }
});

document.addEventListener("DOMContentLoaded", loadQuestions);



