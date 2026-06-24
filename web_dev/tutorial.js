const tutorialSegment = document.getElementById('tutorial-segment')
const tutorialStart = document.getElementById('tutorial-start')
const inputBarTutorial = document.getElementById('input-bar-tutorial')
const inputBarNext = document.getElementById('input-bar-next')
const inputBarPrev = document.getElementById('input-bar-prev')
const singleTutorial = document.getElementById('single-tutorial')
const singleNext = document.getElementById('single-next')
const listTutorial = document.getElementById('list-tutorial')
const listNext = document.getElementById('list-next')
const listPrev = document.getElementById('list-prev')
const csvCheckTutorial = document.getElementById('csv-check-tutorial')
const csvCheckNext = document.getElementById('csv-check-next')
const csvCheckPrev = document.getElementById('csv-check-prev')
const goTutorial = document.getElementById('go-tutorial')
const goNext = document.getElementById('go-next')
const goPrev = document.getElementById('go-prev')
const outputTutorial = document.getElementById('output-tutorial')
const outputNext = document.getElementById('output-next')
const outputPrev = document.getElementById('output-prev')
const changeInputTutorial = document.getElementById('change-input-tutorial')
const changeInputNext = document.getElementById('change-input-next')
const changeInputPrev = document.getElementById('change-input-prev')
const goAgainTutorial = document.getElementById('go-again-tutorial')
const goAgainNext = document.getElementById('go-again-next')
const goAgainPrev = document.getElementById('go-again-prev')
const learnMoreTutorial = document.getElementById('learn-more-tutorial')
const learnMoreNext = document.getElementById('learn-more-next')
const learnMorePrev = document.getElementById('learn-more-prev')
const dataTutorial = document.getElementById('data-tutorial')
const dataNext = document.getElementById('data-next')
const dataPrev = document.getElementById('data-prev')
const informationTutorial = document.getElementById('information-tutorial')
const informationNext = document.getElementById('information-next')
const informationPrev = document.getElementById('information-prev')
const helpPageTutorial = document.getElementById('help-page-tutorial')
const helpPrev = document.getElementById('help-prev')
const sessionHistoryTutorial = document.getElementById('session-history-tutorial')
const sessionHistoryNext = document.getElementById('session-history-next')
const sessionHistoryPrev = document.getElementById('session-history-prev')
const cancels = document.getElementsByClassName('cancel')
const toolTips = document.getElementsByClassName('tool-tip')
const homeButton = document.getElementById('home-button')
const dataButton = document.getElementById('data-button')
const infoButton = document.getElementById('info-button')
const helpButton = document.getElementById('help-button')

const handleBeginTutorialClick = (event) => {
  for (let i = 0; i < toolTips.length; i++) {
    toolTips[i].classList.add("hidden")
  }

  if (inputBar) inputBar.value = ""
  if (csvCheckbox) csvCheckbox.checked = false
  singleButton.click()
  
  if (!explanationModal.classList.contains("hidden")) {
    goBackButton.click()
    outputBox.classList.add("hidden")
    inputBox.classList.remove("moved")
    goButton.textContent = 'Go!'
  }
  
  if (!outputBox.classList.contains("hidden")) {
    outputBox.classList.add("hidden")
    inputBox.classList.remove("moved")
    goButton.textContent = 'Go!'
  }

  if (singleTutorial.classList.contains("hidden")) {
    singleTutorial.classList.remove("hidden")
  }
}

const handleInputNextClick = (event) => {
  inputBarTutorial.classList.add("hidden")
  goTutorial.classList.remove("hidden")
  csvCheckbox.checked = false
  singleButton.click()
  inputBar.value = "Natalus"
}

const handleInputPrevClick = (event) => {
  inputBarTutorial.classList.add("hidden")
  csvCheckTutorial.classList.remove("hidden")
  csvCheckbox.checked = false
  listButton.click()
}

const handleSingleNextClick = (event) => {
  singleTutorial.classList.add("hidden")
  listTutorial.classList.remove("hidden")
}

const handleListNextClick = (event) => {
  listTutorial.classList.add("hidden")
  csvCheckTutorial.classList.remove("hidden")
  listButton.click()
}

const handleListPrevClick = (event) => {
  listTutorial.classList.add("hidden")
  singleTutorial.classList.remove("hidden")
  singleButton.click()
}

const handleCsvCheckNextClick = (event) => {
  csvCheckTutorial.classList.add("hidden")
  inputBarTutorial.classList.remove("hidden")
  csvCheckbox.checked = true
}

const handleCsvCheckPrevClick = (event) => {
  csvCheckTutorial.classList.add("hidden")
  listTutorial.classList.remove("hidden")
  csvCheckbox.checked = false
  singleButton.click()
}

const handleGoNextClick = (event) => {
  goTutorial.classList.add("hidden")
  outputTutorial.classList.remove("hidden")
  goButton.click()
}

const handleGoPrevClick = (event) => {
  goTutorial.classList.add("hidden")
  inputBarTutorial.classList.remove("hidden")
  listButton.click()
  csvCheckbox.checked = true
  inputBar.value = ""
}

const handleOutputNextClick = (event) => {
  outputTutorial.classList.add("hidden")
  changeInputTutorial.classList.remove("hidden")
}

const handleOutputPrevClick = (event) => {
  outputTutorial.classList.add("hidden")
  goTutorial.classList.remove("hidden")
  outputBox.classList.add("hidden")
  inputBox.classList.remove("moved")
  goButton.textContent = "Go!"
}

const handleChangeInputNextClick = (event) => {
  changeInputTutorial.classList.add("hidden")
  goAgainTutorial.classList.remove("hidden")
  inputBar.value = "Different Species"
}

const handleChangeInputPrevClick = (event) => {
  changeInputTutorial.classList.add("hidden")
  outputTutorial.classList.remove("hidden")
}

const handleGoAgainNextClick = (event) => {
  goAgainTutorial.classList.add("hidden")
  sessionHistoryTutorial.classList.remove("hidden")
  goButton.click()
}

const handleGoAgainPrevClick = (event) => {
  goAgainTutorial.classList.add("hidden")
  changeInputTutorial.classList.remove("hidden")
  inputBar.value = "Natalus"
}

const handleSessionHistoryNextClick = (event) => {
  sessionHistoryTutorial.classList.add("hidden")
  learnMoreTutorial.classList.remove("hidden")
  sessionHistoryArrow.click()
}

const handleSessionHistoryPrevClick = (event) => {
  sessionHistoryTutorial.classList.add("hidden")
  goAgainTutorial.classList.remove("hidden")
}

const handleLearnMoreNextClick = (event) => {
  learnMoreTutorial.classList.add("hidden")
  dataTutorial.classList.remove("hidden")
  goBackButton.click()
  learnMoreArrow.click()
  dataButton.classList.add("tutorial-clicked")
}

const handleLearnMorePrevClick = (event) => {
  learnMoreTutorial.classList.add("hidden")
  sessionHistoryTutorial.classList.remove("hidden")
  goBackButton.click()
}

const handleDataNextClick = (event) => {
  dataTutorial.classList.add("hidden")
  informationTutorial.classList.remove("hidden")
  dataButton.classList.remove("tutorial-clicked")
  infoButton.classList.add("tutorial-clicked")
}

const handleDataPrevClick = (event) => {
  dataTutorial.classList.add("hidden")
  learnMoreTutorial.classList.remove("hidden")
  goBackButton.click()
  sessionHistoryArrow.click()
  dataButton.classList.remove("tutorial-clicked")
}

const handleInformationNextClick = (event) => {
  informationTutorial.classList.add("hidden")
  helpPageTutorial.classList.remove("hidden")
  infoButton.classList.remove("tutorial-clicked")
  helpButton.classList.add("tutorial-clicked")
}

const handleInformationPrevClick = (event) => {
  informationTutorial.classList.add("hidden")
  dataTutorial.classList.remove("hidden")
  infoButton.classList.remove("tutorial-clicked")
  dataButton.classList.add("tutorial-clicked")
}

const handleHelpPrevClick = (event) => {
  informationTutorial.classList.remove("hidden")
  helpPageTutorial.classList.add("hidden")
  infoButton.classList.add("tutorial-clicked")
  helpButton.classList.remove("tutorial-clicked")
}

const handleExitTutorialClick = (event) => {
  for (var i = 0; i < toolTips.length; i++) {
    if (!toolTips[i].classList.contains("hidden")) {
      toolTips[i].classList.add("hidden")
    }
  }
  helpButton.classList.remove("tutorial-clicked")
  homeButton.click()
}

for (let i = 0; i < cancels.length; i++) {
  cancels[i].addEventListener("click", handleExitTutorialClick)
}

beginTutorialButton.addEventListener("click", handleBeginTutorialClick)

inputBarNext.addEventListener("click", handleInputNextClick)
singleNext.addEventListener("click", handleSingleNextClick)
listNext.addEventListener("click", handleListNextClick)
csvCheckNext.addEventListener("click", handleCsvCheckNextClick)
outputNext.addEventListener("click", handleOutputNextClick)
goNext.addEventListener("click", handleGoNextClick)
changeInputNext.addEventListener("click", handleChangeInputNextClick)
goAgainNext.addEventListener("click", handleGoAgainNextClick)
sessionHistoryNext.addEventListener("click", handleSessionHistoryNextClick)
learnMoreNext.addEventListener("click", handleLearnMoreNextClick)
dataNext.addEventListener("click", handleDataNextClick)
informationNext.addEventListener("click", handleInformationNextClick)
inputBarPrev.addEventListener("click", handleInputPrevClick)
listPrev.addEventListener("click", handleListPrevClick)
csvCheckPrev.addEventListener("click", handleCsvCheckPrevClick)
outputPrev.addEventListener("click", handleOutputPrevClick)
goPrev.addEventListener("click", handleGoPrevClick)
changeInputPrev.addEventListener("click", handleChangeInputPrevClick)
goAgainPrev.addEventListener("click", handleGoAgainPrevClick)
sessionHistoryPrev.addEventListener("click", handleSessionHistoryPrevClick)
learnMorePrev.addEventListener("click", handleLearnMorePrevClick)
dataPrev.addEventListener("click", handleDataPrevClick)
informationPrev.addEventListener("click", handleInformationPrevClick)
helpPrev.addEventListener("click", handleHelpPrevClick)
