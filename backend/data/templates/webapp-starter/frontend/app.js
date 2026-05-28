async function loadInfo() {
  try {
    const response = await fetch("/api/info");
    if (!response.ok) return;
    const data = await response.json();
    if (data.business_name) {
      document.getElementById("business-name").textContent = data.business_name;
      document.title = data.business_name;
    }
    if (data.tagline) {
      document.getElementById("tagline").textContent = data.tagline;
    }
    const list = document.getElementById("highlights-list");
    list.innerHTML = "";
    const highlights = Array.isArray(data.highlights) && data.highlights.length > 0
      ? data.highlights
      : [
          "Chef-crafted menu with premium ingredients",
          "Elegant interiors and warm hospitality",
          "Seamless online booking with instant confirmation",
        ];
    for (const item of highlights) {
      const li = document.createElement("li");
      li.className = "feature-card";
      li.textContent = typeof item === "string" ? item : item.name || String(item);
      list.appendChild(li);
    }
  } catch {
    /* agents may add /api/info later */
  }
}

document.getElementById("booking-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.target;
  const status = document.getElementById("booking-status");
  const payload = {
    name: form.name.value,
    phone: form.phone.value,
    date: form.date.value,
    party_size: Number(form.party_size.value) || 1,
    notes: form.notes.value,
  };
  const response = await fetch("/api/bookings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    status.textContent = "Could not save booking. Please try again.";
    status.style.color = "#b42318";
    return;
  }
  const data = await response.json();
  status.textContent = `Booking #${data.id} confirmed.`;
  status.style.color = "#087443";
  form.reset();
});

loadInfo();
