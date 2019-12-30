from openpyxl import load_workbook

wb = load_workbook('warnings.xlsx')
ws = wb.active
for row in ws:
    if row[0].value == exampleName:
        name = row[0].value
        warnString = "\n"
        for warn in row[1:]:
            warnString += warn.value + "\n"
        print(name,warnString)
