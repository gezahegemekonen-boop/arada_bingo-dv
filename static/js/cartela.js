const cartela = document.getElementById("cartela");
const bonusGrid = document.getElementById("bonus-numbers");
const winBanner = document.getElementById("win-banner");

let calledNumbers = [];
let interval;
let playMode = "{{ play_mode }}"; // passed from backend
let soundEnabled = {{ 'true' if sound_enabled else 'false' }};

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
      cell.dataset.row = rowIndex;
      cell.dataset.col = colIndex;
      cell.classList.add("cell");

      if (letter === "N" && rowIndex === 2) {
        cell.textContent = "⭐";
        cell.classList.add("free", "marked");
      }

      if (playMode === "manual") {
        cell.addEventListener("click", () => {
          if (calledNumbers.includes(parseInt(cell.dataset.number))) {
            cell.classList.toggle("marked");
            checkWin();
          }
        });
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

    if (soundEnabled) {
      const audio = new Audio(`/static/audio/number_${num}.mp3`);
      audio.play();
    }

    // Mark on cartela (only in auto mode)
    if (playMode === "auto") {
      const cells = cartela.querySelectorAll(".cell");
      cells.forEach(cell => {
        if (cell.dataset.number == num) {
          cell.classList.add("marked");
        }
      });
      checkWin();
    }
  }, Math.floor(Math.random() * 1000) + 3000); // 3–4 sec
}

// Check for Bingo win
function checkWin() {
  const grid = Array.from({ length: 5 }, () => Array(5).fill(false));
  const cells = cartela.querySelectorAll(".cell");

  cells.forEach(cell => {
    const row = parseInt(cell.dataset.row);
    const col = parseInt(cell.dataset.col);
    if (cell.classList.contains("marked")) {
      grid[row][col] = true;
    }
  });

  const isBingo = checkLines(grid);
  if (isBingo) {
    winBanner.style.display = "block";
    clearInterval(interval);
  }
}

function checkLines(grid) {
  for (let i = 0; i < 5; i++) {
    if (grid[i].every(Boolean)) return true; // horizontal
    if (grid.map(row => row[i]).every(Boolean)) return true; // vertical
  }
  if ([0, 1, 2, 3, 4].every(i => grid[i][i])) return true; // diagonal \
  if ([0, 1, 2, 3, 4].every(i => grid[i][4 - i])) return true; // diagonal /
  return false;
}

// Button actions
document.getElementById("refresh").addEventListener("click", () => {
  clearInterval(interval);
  calledNumbers = [];
  bonusGrid.querySelectorAll("button").forEach(btn => btn.style.backgroundColor = "#ff6600");
  winBanner.style.display = "none";
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
