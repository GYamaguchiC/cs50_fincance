# Standard Library Imports
import os, datetime

# Third-Party Package Imports
from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

# Application-Specific Imports
from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    user_id = session.get("user_id")

    # Check balance
    result = db.execute("SELECT cash FROM users WHERE id = :user_id;", user_id=user_id)

    if result:
        balance = result[0]["cash"]

    # Return stocks owned by the user
    stocks = db.execute("SELECT symbol, quantity FROM user_stocks JOIN stocks ON user_stocks.stock_id = stocks.id WHERE user_id = :user_id;", user_id=user_id)
    for stock in stocks:
        stock_info = lookup(stock["symbol"])
        stock["price"] = stock_info["price"]
        stock["total"] = stock["price"] * stock["quantity"]
    return render_template("index.html", stocks=stocks, balance=balance)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    if request.method == "POST":
        symbol = request.form.get("symbol")
        shares = int(request.form.get("shares"))

        # Check for errors
        if shares < 1:
            return apology("The amount needs to be positive")
        elif lookup(symbol) == None:
            return apology("This symbol doesn't exist")

        quote = lookup(symbol)
        if quote is None:
            return apology("This symbol doesn't exist")

        price = quote["price"]
        total = price * shares
        current_date = datetime.date.today()

        user_id = session.get("user_id")
        result = db.execute("SELECT cash FROM users WHERE id = :user_id;", user_id=user_id)

        if result:
            balance = result[0]["cash"]

        # Check if user have enough cash
        if total > balance:
            return apology("You don't have enough cash")

        rows = db.execute("SELECT id FROM stocks WHERE symbol = ?", symbol)

        # If stock is not in db adds it
        if len(rows) == 0:
            db.execute("INSERT INTO stocks(symbol) VALUES(?)", symbol)
            rows = db.execute("SELECT id FROM stocks WHERE symbol = ?", symbol)

        stock_id = rows[0]["id"]

        quantity = db.execute("SELECT quantity FROM user_stocks WHERE user_id = :user_id AND stock_id = :stock_id;", user_id=user_id, stock_id=stock_id)

        if len(quantity) == 0:
            db.execute("INSERT INTO user_stocks(user_id, stock_id, quantity) VALUES(?, ?, ?)", user_id, stock_id, shares)
        else:
            existing_quantity = quantity[0]["quantity"]
            new_quantity = existing_quantity + shares
            db.execute("UPDATE user_stocks SET quantity = :new_quantity WHERE user_id = :user_id AND stock_id = :stock_id;", new_quantity=new_quantity, user_id=user_id, stock_id=stock_id)

        # Add action to history
        db.execute("INSERT INTO actions(user_id, stock_id, action, amount, price, date) VALUES(?, ?, ?, ?, ?, ?)", user_id, stock_id, "Bought", shares, total, current_date)

        # Update balance
        new_balance = balance - total
        db.execute("UPDATE users SET cash = :new_balance WHERE id = :user_id;",new_balance=new_balance, user_id=user_id)

        return redirect("/")

    else:
        return render_template("buy.html")



@app.route("/history")
@login_required
def history():
    user_id = session.get("user_id")
    rows = db.execute("SELECT * FROM actions JOIN stocks ON actions.stock_id = stocks.id WHERE user_id = ? ORDER BY date DESC;", user_id)

    return render_template("history.html", rows=rows)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    if request.method == "POST":
        symbol = request.form.get("symbol")

        # Handling errors
        if not symbol:
            return apology("Please enter a stock symbol")
        quote = lookup(symbol)

        if quote == None:
            return apology("Symbol doesn't exist.")

        return render_template("quoted.html", quote=quote)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        pass_confirm = request.form.get("confirmation")

        # Handling errors
        if not username:
            return apology("Please provide an unsername")
        elif not password:
            return apology("Please provide a password")
        elif not pass_confirm:
            return apology("Please confirm your password")
        elif password != pass_confirm:
            return apology("Password and confirmation don't match")

        rows = db.execute("SELECT username FROM users WHERE username = :username", username=username)

        # Id name is available add to the db
        if len(rows) > 0:
            return apology("Username already exists")
        else:
            hash = generate_password_hash(password)
            db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)", username=username, hash=hash)

        return redirect("/login")
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    if request.method == "POST":
        user_id = session.get("user_id")
        symbol = request.form.get("symbol")
        quantity = db.execute("SELECT quantity FROM user_stocks JOIN stocks ON user_stocks.stock_id = stocks.id  WHERE user_id = :user_id AND symbol = :symbol;", user_id=user_id, symbol=symbol)

        # Handling possible errors
        if (lookup(symbol) is None) or (len(quantity) == 0):
            return apology("This stock symbol doesn't exist or you don't own any of those")

        quantity = quantity[0]["quantity"]
        sell_shares = int(request.form.get("shares"))

        if (sell_shares < 1) or (sell_shares > quantity):
            return apology("Enter a positive number or make sure to sell an amount available in your account")

        # Organizing new information to be updated
        price = lookup(symbol)["price"]
        new_quantity = quantity - sell_shares
        cur_balance = (db.execute("SELECT cash FROM users WHERE id = :user_id;", user_id=user_id))[0]["cash"]
        tot_sell = sell_shares * price
        new_balance = cur_balance + tot_sell
        row = db.execute("SELECT id FROM stocks WHERE symbol = ?;", symbol)
        stock_id = row[0]["id"]
        current_date = datetime.date.today()

        db.execute("UPDATE users SET cash = :new_balance WHERE id = :user_id;", new_balance=new_balance, user_id=user_id)

        # In case there is no more of this stock it is deleted from db
        if new_quantity == 0:
            db.execute("DELETE FROM user_stocks WHERE user_id = :user_id AND stock_id = (SELECT id FROM stocks WHERE symbol = :symbol);", user_id=user_id, symbol=symbol)
        else:
            db.execute("UPDATE user_stocks SET quantity = :new_quantity WHERE user_id = :user_id AND stock_id = (SELECT id FROM stocks WHERE symbol = :symbol);",new_quantity=new_quantity, user_id=user_id, symbol=symbol)

        db.execute("INSERT INTO actions(user_id, stock_id, action, amount, price, date) VALUES (?, ?, ?, ?, ?, ?);", user_id, stock_id, "Sold", sell_shares, tot_sell, current_date)

        return redirect("/")
    else:
        return render_template("sell.html")


@app.route("/password", methods=["GET", "POST"])
@login_required
def password():
    if request.method == "POST":
        prev_pass = request.form.get("prev_password")
        new_pass = request.form.get("new_password")
        pass_confirm = request.form.get("password_confirm")
        user_id = session.get("user_id")

        # Handling possible errors
        if (not prev_pass) or (not new_pass) or (not pass_confirm):
            return apology("Fill all the information")
        elif new_pass != pass_confirm:
            return apology("Password and confirmation don't match")

        rows = db.execute("SELECT * FROM users WHERE id = ?", user_id)

        if not check_password_hash(rows[0]["hash"], prev_pass):
            return apology("Previous password doesn't match")

        hash = generate_password_hash(new_pass)
        db.execute("UPDATE users SET hash = ? WHERE id = ?", hash, user_id)


        return redirect("/")
    else:
        return render_template("password.html")
