# ©️ Dan Gazizullin (hikariatama), 2021-2023
# This file is a part of Hikka Userbot
# 🌐 https://github.com/hikariatama/Hikka
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html
#
# ©️ Codrago, 2024-2030
# This file is a part of Heroku Userbot
# 🌐 https://github.com/coddrago/Heroku
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html
#
# ©️ Wers1xx, 2025-2026
# This file is a part of Hikkari Userbot
# 🌐 https://github.com/Wers1xx/Hikkari
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

import contextlib
import itertools
import os
import subprocess
import sys
import tempfile
import time
import typing
from io import StringIO
from types import ModuleType

import hikkaritl
from hikkaritl.errors.rpcerrorlist import MessageIdInvalidError
from hikkaritl.sessions import StringSession
from hikkaritl.tl.types import Message
from meval import meval

from .. import loader, main, utils
from ..log import HikkariException


@loader.tds
class Evaluator(loader.Module):
    """Evaluates code in various languages"""

    strings = {"name": "Evaluator"}

    class _SecureDB:
        """
        Proxy class to protect sensitive DB fields from eval
        """

        def __init__(self, original_db):
            self._db = original_db

        def __getattr__(self, name):
            return getattr(self._db, name)

        def __getitem__(self, item):
            return self._db[item]

        def set(self, *args, **kwargs):
            if len(args) >= 2 and args[0] == "hikkari.security" and args[1] == "owner":
                raise ValueError(
                    "⚠️ Security Protection: You cannot change the bot owner via evaluator."
                )

            return self._db.set(*args, **kwargs)


    async def _get_reply(self, message: Message):
        """Resolve replied message even if get_reply_message() returns None."""
        reply = None
        with contextlib.suppress(Exception):
            reply = await message.get_reply_message()
        if reply is not None:
            return reply

        reply_to = getattr(message, "reply_to", None)
        if reply_to is None:
            return None

        msg_id = getattr(reply_to, "reply_to_msg_id", None) or getattr(
            reply_to, "reply_to_top_id", None
        )
        if not msg_id:
            return None

        with contextlib.suppress(Exception):
            peer = utils.get_chat_id(message) or message.peer_id
            fetched = await self._client.get_messages(peer, ids=int(msg_id))
            if isinstance(fetched, list):
                return fetched[0] if fetched else None
            return fetched
        return None

    @loader.command(alias="eval")
    async def e(self, message: Message):
        args = utils.get_args_raw(message) or ""
        reply = await self._get_reply(message)

        if not args and reply and (
            getattr(reply, "text", None) or getattr(reply, "message", None)
        ):
            args = reply.message or reply.text or ""

        if not (args or "").strip():
            await utils.answer(
                message,
                "💻 <b>Eval</b>\n"
                "<code>.e &lt;python&gt;</code> or reply to a message with code.\n"
                "Vars: <code>c</code>/<code>client</code>, <code>m</code>/<code>message</code>, "
                "<code>r</code>/<code>reply</code>, <code>db</code>, <code>utils</code>",
            )
            return

        skip_output = args.startswith(("-so ", "--skip-output "))
        if skip_output:
            args = args.split(" ", 1)[1]

        args = args.replace("\xa0", "\x20")

        real_db = self.db
        self.db = self._SecureDB(real_db)

        output_print = StringIO()

        try:
            start_time = time.time()
            with contextlib.redirect_stdout(output_print):
                result = await meval(
                    args,
                    globals(),
                    **await self.getattrs(message),
                )
            print_output = output_print.getvalue()

        except Exception as e:
            item = HikkariException.from_exc_info(*sys.exc_info())
            print_output = output_print.getvalue()
            extra_hint = ""
            if isinstance(e, AttributeError) and "NoneType" in str(e) and (
                "r." in args or "reply." in args
            ):
                extra_hint = (
                    "\n\n💡 <b>Hint:</b> <code>r</code>/<code>reply</code> is "
                    "<code>None</code> — reply to a message when using them."
                )

            await utils.answer(
                message,
                self.strings["err"].format(
                    "4985626654563894116",
                    "python",
                    utils.escape_html(args),
                    "error",
                    self.censor(
                        "\n".join(item.full_stack.splitlines()[:-1])
                        + "\n\n"
                        + "🚫 "
                        + item.full_stack.splitlines()[-1]
                    ),
                )
                + (
                    self.strings["print_outp"].format(
                        "python",
                        utils.escape_html(self.censor(print_output)),
                    )
                    if print_output
                    else ""
                )
                + extra_hint,
            )

            return
        finally:
            self.db = real_db

        if skip_output:
            return

        if callable(getattr(result, "stringify", None)):
            with contextlib.suppress(Exception):
                result = str(result.stringify())

        exec_time = time.time() - start_time

        with contextlib.suppress(MessageIdInvalidError):
            await utils.answer(
                message,
                self.strings["eval_py"].format(
                    "4985626654563894116",
                    "python",
                    utils.escape_html(args),
                )
                + (
                    self.strings["eval_result"].format(
                        "python", utils.escape_html(self.censor(str(result)))
                    )
                    if result or not print_output
                    else ""
                )
                + (
                    self.strings["print_outp"].format(
                        "python",
                        utils.escape_html(self.censor(print_output)),
                    )
                    if print_output
                    else ""
                )
                + (self.strings["time_exec"].format(round(exec_time, 2))),
            )


    @loader.command()
    async def ecpp(self, message: Message, c: bool = False):
        try:
            subprocess.check_output(
                ["gcc" if c else "g++", "--version"],
                stderr=subprocess.STDOUT,
                timeout=10,
            )
        except subprocess.TimeoutExpired:
            await utils.answer(
                message,
                self.strings["no_compiler"].format(
                    "4986046904228905931" if c else "4985844035743646190",
                    "C (gcc)" if c else "C++ (g++)",
                ),
            )
            return
        except Exception:
            await utils.answer(
                message,
                self.strings["no_compiler"].format(
                    "4986046904228905931" if c else "4985844035743646190",
                    "C (gcc)" if c else "C++ (g++)",
                ),
            )
            return

        code = utils.get_args_raw(message)
        message = await utils.answer(message, self.strings["compiling"])
        error = False
        with tempfile.TemporaryDirectory() as tmpdir:
            file = os.path.join(tmpdir, "code.cpp")
            with open(file, "w") as f:
                f.write(code)

            try:
                result = subprocess.check_output(
                    ["gcc" if c else "g++", "-o", "code", "code.cpp"],
                    cwd=tmpdir,
                    stderr=subprocess.STDOUT,
                    timeout=30,
                ).decode()
            except subprocess.CalledProcessError as e:
                result = e.output.decode()
                error = True
            except subprocess.TimeoutExpired:
                result = "Compilation timeout"
                error = True

            if not result:
                try:
                    result = subprocess.check_output(
                        ["./code"],
                        cwd=tmpdir,
                        stderr=subprocess.STDOUT,
                        timeout=10,
                    ).decode()
                except subprocess.CalledProcessError as e:
                    result = e.output.decode()
                    error = True
                except subprocess.TimeoutExpired:
                    result = "Execution timeout"
                    error = True

        with contextlib.suppress(MessageIdInvalidError):
            await utils.answer(
                message,
                self.strings["err" if error else "eval"].format(
                    "4986046904228905931" if c else "4985844035743646190",
                    "c" if c else "cpp",
                    utils.escape_html(code),
                    "error" if error else "output",
                    utils.escape_html(result),
                ),
            )

    @loader.command()
    async def ec(self, message: Message):
        await self.ecpp(message, c=True)

    @loader.command()
    async def ers(self, message: Message):
        try:
            subprocess.check_output(
                ["rustc", "--version"],
                stderr=subprocess.STDOUT,
                timeout=10,
            )
        except subprocess.TimeoutExpired:
            await utils.answer(
                message,
                self.strings["no_compiler"].format(
                    "5424780918776671920",
                    "Rust (rustc)",
                ),
            )
            return
        except Exception:
            await utils.answer(
                message,
                self.strings["no_compiler"].format(
                    "5424780918776671920",
                    "Rust (rustc)",
                ),
            )
            return

        code = utils.get_args_raw(message)
        reply = await message.get_reply_message()

        if not code and reply and reply.text:
            code = reply.message

        message = await utils.answer(message, self.strings["compiling"])
        error = False
        with tempfile.TemporaryDirectory() as tmpdir:
            file = os.path.join(tmpdir, "code.rs")
            with open(file, "w") as f:
                f.write(code)

            try:
                result = subprocess.check_output(
                    ["rustc", "code.rs", "-o", "code"],
                    cwd=tmpdir,
                    stderr=subprocess.STDOUT,
                    timeout=30,
                ).decode()
            except subprocess.CalledProcessError as e:
                result = e.output.decode()
                error = True
            except subprocess.TimeoutExpired:
                result = "Compilation timeout"
                error = True

            if not result:
                try:
                    result = subprocess.check_output(
                        ["./code"],
                        cwd=tmpdir,
                        stderr=subprocess.STDOUT,
                        timeout=10,
                    ).decode()
                except subprocess.CalledProcessError as e:
                    result = e.output.decode()
                    error = True
                except subprocess.TimeoutExpired:
                    result = "Execution timeout"
                    error = True

        with contextlib.suppress(MessageIdInvalidError):
            await utils.answer(
                message,
                self.strings["err" if error else "eval"].format(
                    "5424780918776671920",
                    "rust",
                    utils.escape_html(code),
                    "error" if error else "output",
                    utils.escape_html(result),
                ),
            )

    @loader.command()
    async def eg(self, message: Message):
        try:
            subprocess.check_output(
                ["go", "version"],
                stderr=subprocess.STDOUT,
                timeout=10,
            )
        except subprocess.TimeoutExpired:
            await utils.answer(
                message,
                self.strings["no_compiler"].format(
                    "4994652309293105740",
                    "Go",
                ),
            )
            return
        except Exception:
            await utils.answer(
                message,
                self.strings["no_compiler"].format(
                    "4994652309293105740",
                    "Go",
                ),
            )
            return

        code = utils.get_args_raw(message)
        reply = await message.get_reply_message()

        if not code and reply and reply.text:
            code = reply.message

        message = await utils.answer(message, self.strings["compiling"])
        error = False
        with tempfile.TemporaryDirectory() as tmpdir:
            file = os.path.join(tmpdir, "code.go")
            with open(file, "w") as f:
                f.write(code)

            try:
                result = subprocess.check_output(
                    ["go", "run", "code.go"],
                    cwd=tmpdir,
                    stderr=subprocess.STDOUT,
                    timeout=30,
                ).decode()
            except subprocess.CalledProcessError as e:
                result = e.output.decode()
                error = True
            except subprocess.TimeoutExpired:
                result = "Execution timeout"
                error = True

        with contextlib.suppress(MessageIdInvalidError):
            await utils.answer(
                message,
                self.strings["err" if error else "eval"].format(
                    "4994652309293105740",
                    "go",
                    utils.escape_html(code),
                    "error" if error else "output",
                    utils.escape_html(result),
                ),
            )

    @loader.command()
    async def enode(self, message: Message):
        try:
            subprocess.check_output(
                ["node", "--version"],
                stderr=subprocess.STDOUT,
                timeout=10,
            )
        except subprocess.TimeoutExpired:
            await utils.answer(
                message,
                self.strings["no_compiler"].format(
                    "4985643941807260310",
                    "Node.js",
                ),
            )
            return
        except Exception:
            await utils.answer(
                message,
                self.strings["no_compiler"].format(
                    "4985643941807260310",
                    "Node.js",
                ),
            )
            return

        code = utils.get_args_raw(message)
        error = False
        with tempfile.TemporaryDirectory() as tmpdir:
            file = os.path.join(tmpdir, "code.js")
            with open(file, "w") as f:
                f.write(code)

            try:
                result = subprocess.check_output(
                    ["node", "code.js"],
                    cwd=tmpdir,
                    stderr=subprocess.STDOUT,
                    timeout=10,
                ).decode()
            except subprocess.CalledProcessError as e:
                result = e.output.decode()
                error = True
            except subprocess.TimeoutExpired:
                result = "Execution timeout"
                error = True

        with contextlib.suppress(MessageIdInvalidError):
            await utils.answer(
                message,
                self.strings["err" if error else "eval"].format(
                    "4985643941807260310",
                    "javascript",
                    utils.escape_html(code),
                    "error" if error else "output",
                    utils.escape_html(result),
                ),
            )

    def censor(self, ret: str) -> str:
        ret = ret.replace(str(self._client.hikkari_me.phone), "&lt;phone&gt;")

        if redis := os.environ.get("REDIS_URL") or main.get_config_key("redis_uri"):
            ret = ret.replace(redis, f'redis://{"*" * 26}')

        if db := os.environ.get("DATABASE_URL") or main.get_config_key("db_uri"):
            ret = ret.replace(db, f'postgresql://{"*" * 26}')

        if btoken := self._db.get("hikkari.inline", "bot_token", False):
            ret = ret.replace(
                btoken,
                f'{btoken.split(":")[0]}:{"*" * 26}',
            )

        if htoken := self.lookup("LoaderMod").get("token", False):
            ret = ret.replace(htoken, f'eugeo_{"*" * 26}')

        ret = ret.replace(
            StringSession.save(self._client.session),
            "StringSession(**************************)",
        )

        return ret

    async def getattrs(self, message: Message) -> dict:
        reply = await self._get_reply(message)
        math_ns = self._math_namespace()
        return {
            "message": message,
            "client": self._client,
            "reply": reply,
            "r": reply,
            "event": message,
            "chat": message.to_id,
            "hikkaritl": hikkaritl,
            "telethon": hikkaritl,
            "hikkatl": hikkaritl,
            "utils": utils,
            "main": main,
            "loader": loader,
            "c": self._client,
            "m": message,
            "lookup": self.lookup,
            "self": self,
            "db": self.db,
            **math_ns,
            **self.get_sub(hikkaritl.tl.functions),
            **self.get_sub(hikkaritl.tl.types),
        }


    async def _ensure_sympy(self) -> bool:
        """Install sympy + mpmath (venv-aware, no --user in venv)."""
        import logging
        import subprocess
        import sys

        log = logging.getLogger(__name__)
        is_venv = hasattr(sys, "real_prefix") or (
            hasattr(sys, "base_prefix") and sys.prefix != sys.base_prefix
        )
        use_user = (
            not is_venv
            and "VIRTUAL_ENV" not in os.environ
            and "PIP_TARGET" not in os.environ
        )
        cmd = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "-q",
            "--disable-pip-version-check",
            "--no-warn-script-location",
            "--prefer-binary",
            *(["--user"] if use_user else []),
            "sympy>=1.12",
            "mpmath>=1.3.0",
        ]
        try:
            r = await utils.run_sync(
                subprocess.run,
                cmd,
                check=False,
                capture_output=True,
                timeout=300,
            )
            if r.returncode != 0:
                err = ((r.stderr or r.stdout) or b"").decode(errors="ignore")
                log.error("sympy install failed: %s", err[-800:])
                return False
            return True
        except Exception:
            log.exception("sympy install exception")
            return False

    def _math_namespace(self) -> dict:
        """Rich math context for .e and .calc (sympy + stdlib)."""
        import math
        import cmath
        import statistics
        from decimal import Decimal, getcontext
        from fractions import Fraction

        getcontext().prec = 80
        ns: dict = {
            "math": math,
            "cmath": cmath,
            "statistics": statistics,
            "Decimal": Decimal,
            "Fraction": Fraction,
            # common shortcuts
            "sqrt": math.sqrt,
            "sin": math.sin,
            "cos": math.cos,
            "tan": math.tan,
            "log": math.log,
            "log10": math.log10,
            "log2": math.log2,
            "exp": math.exp,
            "pi": math.pi,
            "e": math.e,
            "tau": math.tau,
            "inf": math.inf,
            "nan": math.nan,
            "factorial": math.factorial,
            "gcd": math.gcd,
            "lcm": getattr(math, "lcm", None),
            "comb": getattr(math, "comb", None),
            "perm": getattr(math, "perm", None),
            "degrees": math.degrees,
            "radians": math.radians,
            "fabs": math.fabs,
            "ceil": math.ceil,
            "floor": math.floor,
            "pow": pow,
            "abs": abs,
            "round": round,
            "sum": sum,
            "min": min,
            "max": max,
        }
        # drop None helpers on older Python
        ns = {k: v for k, v in ns.items() if v is not None}

        try:
            import sympy as sp
            from sympy import (
                symbols,
                Symbol,
                Function,
                Eq,
                solve,
                solveset,
                nsolve,
                dsolve,
                simplify,
                expand,
                factor,
                collect,
                cancel,
                together,
                apart,
                trigsimp,
                powsimp,
                logcombine,
                limit,
                series,
                diff,
                integrate,
                summation,
                product,
                Matrix,
                eye,
                zeros,
                ones,
                det,
                inv,
                transpose,
                latex,
                pretty,
                N,
                oo,
                zoo,
                I,
                E,
                pi as spi,
                E as sE,
                sin as ssin,
                cos as scos,
                tan as stan,
                asin,
                acos,
                atan,
                atan2,
                sinh,
                cosh,
                tanh,
                exp as sexp,
                log as slog,
                sqrt as ssqrt,
                root,
                Pow,
                Integer,
                Rational,
                Float,
                Abs,
                re,
                im,
                arg,
                conjugate,
                factorial as sfactorial,
                binomial,
                fibonacci,
                primerange,
                isprime,
                factorint,
                gcd as sgcd,
                lcm as slcm,
                floor as sfloor,
                ceiling,
                Mod,
                Sum,
                Product,
                Integral,
                Derivative,
                Lambda,
                Piecewise,
                Heaviside,
                DiracDelta,
                gamma,
                beta,
                zeta,
                erf,
                erfc,
                Si,
                Ci,
                expint,
            )

            # Prefer sympy for symbolic names (override stdlib math shortcuts)
            ns.update(
                {
                    "sin": ssin,
                    "cos": scos,
                    "tan": stan,
                    "exp": sexp,
                    "log": slog,
                    "sqrt": ssqrt,
                    "pi": spi,
                    "e": sE,
                    "factorial": sfactorial,
                    "sympy": sp,
                    "sp": sp,
                    "symbols": symbols,
                    "Symbol": Symbol,
                    "Function": Function,
                    "Eq": Eq,
                    "solve": solve,
                    "solveset": solveset,
                    "nsolve": nsolve,
                    "dsolve": dsolve,
                    "simplify": simplify,
                    "expand": expand,
                    "factor": factor,
                    "collect": collect,
                    "cancel": cancel,
                    "together": together,
                    "apart": apart,
                    "trigsimp": trigsimp,
                    "powsimp": powsimp,
                    "logcombine": logcombine,
                    "limit": limit,
                    "series": series,
                    "diff": diff,
                    "integrate": integrate,
                    "summation": summation,
                    "product": product,
                    "Matrix": Matrix,
                    "eye": eye,
                    "zeros": zeros,
                    "ones": ones,
                    "det": det,
                    "inv": inv,
                    "transpose": transpose,
                    "latex": latex,
                    "pretty": pretty,
                    "N": N,
                    "oo": oo,
                    "zoo": zoo,
                    "I": I,
                    "E": E,
                    "spi": spi,
                    "ssin": ssin,
                    "scos": scos,
                    "stan": stan,
                    "asin": asin,
                    "acos": acos,
                    "atan": atan,
                    "atan2": atan2,
                    "sinh": sinh,
                    "cosh": cosh,
                    "tanh": tanh,
                    "sexp": sexp,
                    "slog": slog,
                    "ssqrt": ssqrt,
                    "root": root,
                    "Pow": Pow,
                    "Integer": Integer,
                    "Rational": Rational,
                    "Float": Float,
                    "Abs": Abs,
                    "re": re,
                    "im": im,
                    "arg": arg,
                    "conjugate": conjugate,
                    "sfactorial": sfactorial,
                    "binomial": binomial,
                    "fibonacci": fibonacci,
                    "primerange": primerange,
                    "isprime": isprime,
                    "factorint": factorint,
                    "sgcd": sgcd,
                    "slcm": slcm,
                    "sfloor": sfloor,
                    "ceiling": ceiling,
                    "Mod": Mod,
                    "Sum": Sum,
                    "Product": Product,
                    "Integral": Integral,
                    "Derivative": Derivative,
                    "Lambda": Lambda,
                    "Piecewise": Piecewise,
                    "Heaviside": Heaviside,
                    "DiracDelta": DiracDelta,
                    "gamma": gamma,
                    "beta": beta,
                    "zeta": zeta,
                    "erf": erf,
                    "erfc": erfc,
                    "Si": Si,
                    "Ci": Ci,
                    "expint": expint,
                    # prefer sympy pi/E when both present for symbolic work
                    "S": sp.S,
                }
            )
        except ImportError:
            ns["_sympy_missing"] = True

        try:
            import mpmath as mp

            mp.mp.dps = 50
            ns["mpmath"] = mp
            ns["mp"] = mp
        except ImportError:
            pass

        try:
            import numpy as np

            ns["numpy"] = np
            ns["np"] = np
        except ImportError:
            pass

        return ns

    def _format_math_result(self, result) -> str:
        """Pretty-print sympy / numeric results."""
        if result is None:
            return "None"
        try:
            import sympy as sp

            if isinstance(result, sp.Basic):
                try:
                    text = sp.pretty(result, use_unicode=True)
                except Exception:
                    text = str(result)
                # also numeric approx when possible
                try:
                    num = sp.N(result, 20)
                    if num != result and not num.free_symbols:
                        text = f"{text}\n≈ {num}"
                except Exception:
                    pass
                return text
            if isinstance(result, (list, tuple)) and result and all(
                isinstance(x, sp.Basic) for x in result
            ):
                parts = []
                for i, x in enumerate(result):
                    try:
                        parts.append(f"[{i}] {sp.pretty(x, use_unicode=True)}")
                    except Exception:
                        parts.append(f"[{i}] {x}")
                return "\n".join(parts)
        except Exception:
            pass
        return str(result)

    @loader.command(alias="calculator")
    async def calc(self, message: Message):
        """Advanced symbolic calculator (sympy).
        Examples:
        .calc integrate(x**2, x)
        .calc solve(x**2 - 5*x + 6, x)
        .calc diff(sin(x)**2, x)
        .calc limit(sin(x)/x, x, 0)
        .calc Matrix([[1,2],[3,4]]).inv()
        .calc N(pi, 50)
        """
        args = utils.get_args_raw(message) or ""
        reply = await self._get_reply(message)
        if not args.strip() and reply and (getattr(reply, "text", None) or getattr(reply, "message", None)):
            args = reply.message or reply.text or ""
        args = (args or "").replace("\xa0", " ").strip()
        if not args:
            await utils.answer(
                message,
                "🧮 <b>Calc</b> — symbolic engine (sympy)\n\n"
                "<code>.calc integrate(x**2, x)</code>\n"
                "<code>.calc solve([x**2-5*x+6], x)</code>\n"
                "<code>.calc diff(sin(x)**2, x)</code>\n"
                "<code>.calc limit(sin(x)/x, x, 0)</code>\n"
                "<code>.calc series(exp(x), x, 0, 6)</code>\n"
                "<code>.calc N(pi, 40)</code>\n"
                "<code>.calc Matrix([[1,2],[3,4]]).det()</code>\n"
                "<code>.calc factor(x**3-1)</code>\n"
                "<code>.calc simplify((x**2-1)/(x-1))</code>\n\n"
                "Also available in <code>.e</code>: sympy, sp, solve, diff, integrate, Matrix, N, …",
            )
            return

        ns = self._math_namespace()
        if ns.get("_sympy_missing"):
            await utils.answer(
                message,
                "⏳ <b>Installing sympy + mpmath…</b>",
            )
            ok = await self._ensure_sympy()
            if not ok:
                await utils.answer(
                    message,
                    "🚫 <b>sympy</b> install failed.\n"
                    "Run: <code>pip install sympy mpmath</code>",
                )
                return
            ns = self._math_namespace()
            if ns.get("_sympy_missing"):
                await utils.answer(
                    message,
                    "🚫 <b>sympy</b> still missing. Restart userbot.",
                )
                return

        # Pre-declare common symbols so bare x,y,z work
        try:
            import sympy as sp

            for name in ("x", "y", "z", "t", "n", "k", "a", "b", "c", "m"):
                ns[name] = sp.symbols(name, real=True)
            ns["theta"] = sp.symbols("theta", real=True)
            ns["phi"] = sp.symbols("phi", real=True)
        except Exception:
            pass

        start = time.time()
        try:
            result = eval(compile(args, "<calc>", "eval"), {"__builtins__": {}}, ns)
            text = self._format_math_result(result)
            took = round(time.time() - start, 3)
            if len(text) > 3500:
                text = text[:3500] + "\n…"
            await utils.answer(
                message,
                f"🧮 <b>Calc</b>\n"
                f"<code>{utils.escape_html(args)}</code>\n\n"
                f"<b>Result:</b>\n<code>{utils.escape_html(text)}</code>\n\n"
                f"⏱ <code>{took}s</code>",
            )
        except Exception as e:
            await utils.answer(
                message,
                f"🧮 <b>Calc error</b>\n<code>{utils.escape_html(args)}</code>\n\n"
                f"🚫 <code>{utils.escape_html(type(e).__name__)}: {utils.escape_html(str(e))}</code>",
            )

    def get_sub(self, obj: typing.Any, _depth: int = 1) -> dict:
        """Get all callable capitalised objects in an object recursively, ignoring _*"""
        return {
            **dict(
                filter(
                    lambda x: x[0][0] != "_"
                    and x[0][0].upper() == x[0][0]
                    and callable(x[1]),
                    obj.__dict__.items(),
                )
            ),
            **dict(
                itertools.chain.from_iterable(
                    [
                        self.get_sub(y[1], _depth + 1).items()
                        for y in filter(
                            lambda x: x[0][0] != "_"
                            and isinstance(x[1], ModuleType)
                            and x[1] != obj
                            and x[1].__package__.rsplit(".", _depth)[0]
                            == "hikkaritl.tl",
                            obj.__dict__.items(),
                        )
                    ]
                )
            ),
        }
