const cartela = document.getElementById("cartela");
const bonusGrid = document.getElementById("bonus-numbers");

let calledNumbers = [];
let interval;

// Generate Bonus Grid (1–75)
for (let i = 1; i <= 75; i++) {
  const btn = document.createElement("button");
  btn.textContent = i;
  btn.id = `bonus-${i}`;
  bonusGrid.appendChild(btn);
}

// Generate Cartela (5x5 Bingo)
function generateCartela() {
  cartela.innerHTML = "";
  const ranges = {
    B: [1, 15],
    I: [16, 30],
    N: [31, 45],
    G: [46, 60],
    O: [61, 75]
  };

  Object.keys(ranges).forEach((letter, colIndex) => {
    let nums = [];
    while (nums.length < 5) {
      const num = Math.floor(Math.random() * (ranges[letter][1] - ranges[letter][0] + 1)) + ranges[letter][0];
      if (!nums.includes(num)) nums.push(num);
    }

    nums.forEach((num, rowIndex) => {
      const cell = document.createElement("div");
      cell.textContent = num;
      cell.dataset.number = num;
      if (letter === "N" && rowIndex === 2) {
        cell.textContent = "⭐";
        cell.classList.add("free");
      }
      cartela.appendChild(cell);
    });
  });
}

generateCartela();

// Call Numbers Every 3–4 Seconds
function startCalling() {
  interval = setInterval(() => {
    let num;
    do {
      num = Math.floor(Math.random() * 75) + 1;
    } while (calledNumbers.includes(num));

    calledNumbers.push(num);
    document.getElementById(`bonus-${num}`).style.backgroundColor = "#4caf50";

    // Mark on cartela
    const cells = cartela.querySelectorAll("div");
    cells.forEach(cell => {
      if (cell.dataset.number == num) {
        cell.classList.add("marked");
      }
    });

    // Optional: Check for Bingo win here
  }, Math.floor(Math.random() * 1000) + 3000); // 3–4 sec
}

document.getElementById("refresh").addEventListener("click", () => {
  clearInterval(interval);
  calledNumbers = [];
  bonusGrid.querySelectorAll("button").forEach(btn => btn.style.backgroundColor = "#ff6600");
  generateCartela();
  startCalling();
});

document.getElementById("add-cartela").addEventListener("click", () => {
  alert("➕ Add Cartela feature coming soon!");
});

document.getElementById("bingo").addEventListener("click", () => {
  alert("🎉 Bingo claimed! Admin will verify.");
});

startCalling();

