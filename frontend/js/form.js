const STATES = [
  "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa",
  "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala",
  "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland",
  "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura",
  "Uttar Pradesh", "Uttarakhand", "West Bengal",
  "Andaman and Nicobar Islands", "Chandigarh", "Dadra and Nagar Haveli and Daman and Diu",
  "Delhi", "Jammu and Kashmir", "Ladakh", "Lakshadweep", "Puducherry",
];

function populateStates() {
  const select = document.getElementById("state");
  select.innerHTML = '<option value="">Select your state / UT</option>' +
    STATES.map((s) => `<option value="${s}">${s}</option>`).join("");
}

function setSerial() {
  const serial = "SS-" + Math.floor(100000 + Math.random() * 899999);
  document.getElementById("form-serial").textContent = "FILE #" + serial;
}

function showError(msg) {
  const el = document.getElementById("form-error");
  el.textContent = msg;
  el.style.display = "block";
}

function hideError() {
  document.getElementById("form-error").style.display = "none";
}

function readProfile() {
  const form = document.getElementById("profile-form");
  const data = new FormData(form);
  return {
    age: data.get("age") ? Number(data.get("age")) : null,
    gender: data.get("gender") || null,
    state: data.get("state") || null,
    occupation: data.get("occupation") || null,
    income_annual: data.get("income") ? Number(data.get("income")) : null,
    social_category: data.get("category") || null,
    language: SSAI.getLang(),
  };
}

async function handleSubmit(event) {
  event.preventDefault();
  hideError();

  const profile = readProfile();
  if (!profile.age || !profile.state || !profile.occupation) {
    showError("Please fill in age, state and occupation — these are needed to match you accurately.");
    return;
  }

  const btn = document.getElementById("submit-btn");
  const originalLabel = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Checking…";

  try {
    const result = await SSAI_API.matchSchemes(profile);
    sessionStorage.setItem("ssai_profile", JSON.stringify(profile));
    sessionStorage.setItem("ssai_result", JSON.stringify(result));
    window.location.href = "results.html";
  } catch (err) {
    console.error(err);
    showError("Something went wrong reaching the matching service. Please make sure the backend server is running and try again.");
    btn.disabled = false;
    btn.textContent = originalLabel;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  populateStates();
  setSerial();
  document.getElementById("profile-form").addEventListener("submit", handleSubmit);
});
