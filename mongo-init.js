db = db.getSiblingDB('pollmaster');

db.createUser(
	{
		user: "pm",
		pwd: "pwdhere",
		roles: [
			{
				role: "dbOwner",
				db: "pollmaster"
			}
		]
	}
);

