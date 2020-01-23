import pickle
import os

memberList = []

member = [12,"Twan","Warn 1","Warn 2","Warn 3"]
memberList.append(member)

member = ['123123123123213', "Jakob", "Warn 1"]
memberList.append(member)

pickle.dump(memberList,open("members.dat","wb"))

memberList = pickle.load(open("members.dat", "rb"))

for member in memberList:
    counter = 0
    try:
        if member[0] == 12:
            memberList.remove(memberList[counter])
            pickle.dump(memberList, open("members.dat", "wb"))
    except ValueError:
        counter += 1

memberList = pickle.load(open("members.dat", "rb"))
print(memberList)

