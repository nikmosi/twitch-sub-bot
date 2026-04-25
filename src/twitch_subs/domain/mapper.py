from twitch_subs.domain.models import LoginStatus, UserRecord


def user_record_to_login_status(ur: UserRecord) -> LoginStatus:
    return LoginStatus(
        login=ur.login,
        broadcaster_type=ur.broadcaster_type,
        user=ur,
    )
