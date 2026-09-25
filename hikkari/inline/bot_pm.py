import logging
import typing

from .types import InlineUnit

if typing.TYPE_CHECKING:
    from ..inline.core import InlineManager

logger = logging.getLogger(__name__)


class BotPM(InlineUnit):
    def set_fsm_state(
        self: "InlineManager",
        user: str | int,
        state: str | bool,
    ) -> bool:
        """
        Set FSM state for user
        :param user: user id
        :param state: state to set
        :return: True if state was set, False otherwise
        :rtype: bool
        """
        if not isinstance(user, (str, int)):
            logger.error(
                (
                    "Invalid type for `user` in `set_fsm_state`. Expected `str` or"
                    " `int`, got %s"
                ),
                type(user),
            )
            return False

        if not isinstance(state, (str, bool)):
            logger.error(
                (
                    "Invalid type for `state` in `set_fsm_state`. Expected `str` or"
                    " `bool`, got %s"
                ),
                type(state),
            )
            return False

        match True:
            case _ if state:
                self.fsm[str(user)] = state
            case _ if str(user) in self.fsm:
                del self.fsm[str(user)]

        return True

    ss = set_fsm_state

    def get_fsm_state(self: "InlineManager", user: str | int) -> bool | str:
        """
        Get FSM state for user
        :param user: user id
        :return: FSM state or False if user has no FSM state
        :rtype: typing.Union[bool, str]
        """
        if not isinstance(user, (str, int)):
            logger.error(
                (
                    "Invalid type for `user` in `get_fsm_state`. Expected `str` or"
                    " `int`, got %s"
                ),
                type(user),
            )
            return False

        return self.fsm.get(str(user), False)

    gs = get_fsm_state
