import openpyxl

wb = openpyxl.load_workbook('warnings.xlsx')
ws = wb.active

for row in ws: 
    givenName = "TheDankestPutin#1389"
    warnReason = "Retarded"
    if row[0].value == givenName:
        for warn in row[1:]:
            if type(warn.value) == type(None):
                cell = (str(warn)[-3:-1])
                ws[cell] = warnReason
                wb.save('warnings.xlsx')
                return

