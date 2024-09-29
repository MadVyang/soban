import datetime
import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# Calendar API에 접근할 범위를 설정합니다.
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']


def get_holidays(service, start_of_month, end_of_month):
    """공휴일 목록을 가져오는 함수입니다."""
    holiday_calendar_id = 'ko.south_korea#holiday@group.v.calendar.google.com'
    holidays_result = service.events().list(calendarId=holiday_calendar_id,
                                            timeMin=start_of_month,
                                            timeMax=end_of_month,
                                            singleEvents=True,
                                            orderBy='startTime').execute()
    holidays = holidays_result.get('items', [])

    holiday_dates = {}
    for event in holidays:
        start_time = event['start'].get('dateTime', event['start'].get('date'))
        start_date = datetime.datetime.fromisoformat(
            start_time[:-1]) if start_time.endswith('Z') else datetime.datetime.fromisoformat(start_time)
        holiday_dates[start_date.date()] = event['summary']  # 날짜와 휴일 이름 저장

    return holiday_dates


def get_events(service, target_calendar_id, start_of_month, end_of_month):
    """특정 캘린더에서 이벤트 목록을 가져오는 함수입니다."""
    events_result = service.events().list(calendarId=target_calendar_id,
                                          timeMin=start_of_month,
                                          timeMax=end_of_month,
                                          maxResults=100, singleEvents=True,
                                          orderBy='startTime').execute()
    return events_result.get('items', [])


def read_calendar_id():
    """캘린더 ID를 파일에서 읽어오는 함수입니다."""
    with open('calendar_id.txt', 'r') as f:
        return f.read().strip()


def read_members():
    """멤버 목록을 파일에서 읽어오는 함수입니다."""
    with open('members.txt', 'r', encoding='utf-8') as f:
        return [line.strip() for line in f.readlines()]


def read_total_cost():
    """총 식사 비용을 파일에서 읽어오는 함수입니다."""
    with open('total_cost.txt', 'r', encoding='utf-8') as f:
        return int(f.read().strip())


def calculate_meal_costs(events, holiday_dates, members, total_cost):
    """각 멤버의 최종 부담 비용을 계산하는 함수입니다."""
    weekdays = [0, 1, 2, 3]  # 월요일: 0, 화요일: 1, 수요일: 2, 목요일: 3
    meals_per_day = {}
    # 기본적으로 공휴일에는 아무도 식사하지 않음
    meal_attendance = {date: set(members) for date in holiday_dates.keys()}

    # 월요일부터 목요일까지 체크
    for day in range(1, 32):
        try:
            date = datetime.date(datetime.datetime.now(
            ).year, datetime.datetime.now().month, day)
            if date.weekday() in weekdays:
                meals_per_day[date] = set(members)  # 기본적으로 모든 멤버가 식사하는 것으로 초기화
                meal_attendance[date] = set(members)  # 기본적으로 모든 멤버가 참석한다고 가정
        except ValueError:
            continue

    for event in events:
        start_time = event['start'].get('dateTime', event['start'].get('date'))
        end_time = event['end'].get('dateTime', event['end'].get('date'))

        if 'Z' not in start_time:
            start_time += 'Z'
        if 'Z' not in end_time:
            end_time += 'Z'

        start_date = datetime.datetime.fromisoformat(start_time[:-1]).date()
        end_date = datetime.datetime.fromisoformat(end_time[:-1]).date()

        # 각 날짜를 체크하여 누가 식사를 빠졌는지 업데이트
        for single_date in (start_date + datetime.timedelta(n) for n in range((end_date - start_date).days + 1)):
            if single_date in meals_per_day:
                missed_people = event['summary'].split(',')
                for person in missed_people:
                    meals_per_day[single_date].discard(person.strip())
                    meal_attendance[single_date].discard(
                        person.strip())  # 식사 안 한 사람 기록

    # 식사 수를 계산합니다.
    total_meals = 0
    meal_count_per_member = {member: 0 for member in members}

    for day in meals_per_day:
        attendees = meals_per_day[day]
        if attendees and day not in holiday_dates:  # 식사에 참석한 멤버가 있을 경우, 공휴일 제외
            meal_count = len(attendees)
            total_meals += meal_count

            for member in attendees:
                meal_count_per_member[member] += 1

    # 각 멤버가 지불해야 할 비용을 계산합니다.
    cost_per_meal = total_cost / total_meals if total_meals > 0 else 0
    costs = {member: meal_count_per_member[member]
             * cost_per_meal for member in members}

    return costs, meal_attendance, meal_count_per_member, cost_per_meal


def get_korean_weekday(date):
    """날짜에 대한 한국어 요일을 반환하는 함수입니다."""
    weekdays_korean = ['월', '화', '수', '목', '금', '토', '일']
    return weekdays_korean[date.weekday()]


def main():
    # 인증 정보 파일을 불러옵니다.
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    # Google Calendar API 클라이언트를 빌드합니다.
    service = build('calendar', 'v3', credentials=creds)

    # 이번 달의 시작과 끝 날짜를 설정합니다.
    now = datetime.datetime.utcnow()
    start_of_month = datetime.datetime(
        now.year, now.month, 1).isoformat() + 'Z'
    end_of_month = (datetime.datetime(now.year, now.month + 1,
                    1) - datetime.timedelta(days=1)).isoformat() + 'Z'

    print(
        f'Getting events from {start_of_month} to {end_of_month} (Monday to Thursday, excluding holidays)')

    # 공휴일 목록을 가져옵니다.
    holiday_dates = get_holidays(service, start_of_month, end_of_month)

    # 캘린더 ID를 파일에서 읽어옵니다.
    target_calendar_id = read_calendar_id()
    events = get_events(service, target_calendar_id,
                        start_of_month, end_of_month)

    # 멤버 목록과 총 비용을 파일에서 읽어옵니다.
    members = read_members()
    total_cost = read_total_cost()

    # 각 멤버의 비용을 계산합니다.
    costs, meal_attendance, meal_count_per_member, cost_per_meal = calculate_meal_costs(
        events, holiday_dates, members, total_cost)

    # 결과를 파일로 저장합니다.
    with open('meal_costs_result.txt', 'w', encoding='utf-8') as f:
        f.write("날짜별 식사 참여자:\n")

        # 이번 달의 모든 날짜에 대해 체크
        for day in range(1, 32):
            try:
                date = datetime.date(datetime.datetime.now(
                ).year, datetime.datetime.now().month, day)
                day_of_week = get_korean_weekday(date)

                if date in holiday_dates:
                    f.write(
                        f"{date}({day_of_week}) - ({holiday_dates[date]})\n")
                elif date in meal_attendance:
                    attendees = sorted(
                        meal_attendance[date], key=lambda x: members.index(x))  # 입력된 순서대로 정렬
                    f.write(
                        f"{date}({day_of_week}) - {' '.join(attendees)}\n")
            except ValueError:
                continue  # 잘못된 날짜는 무시

        f.write("\n한 끼니당 비용: {:.2f} 원\n\n".format(cost_per_meal))
        f.write("각 멤버의 부담 비용:\n")
        for member in members:  # 입력된 순서대로 출력
            f.write(
                f"{member}: {costs[member]:.2f} 원, 식사 횟수: {meal_count_per_member[member]} 회\n")

    print("결과가 meal_costs_result.txt 파일에 저장되었습니다.")


if __name__ == '__main__':
    main()
