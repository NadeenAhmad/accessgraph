// Receives the reviewers' answers from the D5 review site and adds one row per answer to the first sheet.
// Setup (once): Google Sheet -> Extensions -> Apps Script -> paste this -> Deploy -> New deployment ->
// type "Web app", execute as "Me", who has access "Anyone" -> Deploy -> copy the web app URL.
function doPost(e) {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheets()[0];
  if (sheet.getLastRow() === 0) {
    sheet.appendRow(['received', 'reviewer', 'item', 'answer', 'reason', 'seconds', 'answered_at']);
  }
  var r = JSON.parse(e.postData.contents);
  sheet.appendRow([new Date(), r.reviewer, r.item, r.answer, r.reason, r.seconds, r.at]);
  return ContentService.createTextOutput('ok');
}
