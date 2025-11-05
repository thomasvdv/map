#!/usr/bin/env python3
"""
        Check if a date has been processed.

        Args:
            date_str: Date in YYYY-MM-DD format

        Returns:
            True if date has flights recorded
        """
        return date_str in self.state['processed_dates']

    def get_new_flights(self, all_flights: List[str]) -> List[str]:
        """
        Filter list of flights to only those not yet processed.

        Args:
            all_flights: List of flight filenames

        Returns:
            List of new flight filenames
        """
        return [f for f in all_flights if not self.is_flight_processed(f)]

    def get_new_dates(self, all_dates: Set[str]) -> Set[str]:
        """
        Filter set of dates to only those not yet processed.

        Args:
            all_dates: Set of dates in YYYY-MM-DD format

        Returns:
            Set of new dates
        """
        return {d for d in all_dates if not self.is_date_processed(d)}

    def mark_flight_processed(
        self,
        flight_filename: str,
        date_str: str,
        uploaded_to_r2: bool = True
    ) -> None:
        """
        Mark a flight as processed.

        Args:
            flight_filename: IGC filename
            date_str: Flight date in YYYY-MM-DD format
            uploaded_to_r2: Whether file was uploaded to R2
        """
        self.state['processed_flights'][flight_filename] = {
            'date': date_str,
            'uploaded_to_r2': uploaded_to_r2,
            'processed_at': datetime.utcnow().isoformat() + 'Z'
        }

        # Also add to date's flight list
        if date_str not in self.state['processed_dates']:
            self.state['processed_dates'][date_str] = {
                'flights': [],
                
                'last_processed': None
            }

        if flight_filename not in self.state['processed_dates'][date_str]['flights']:
            self.state['processed_dates'][date_str]['flights'].append(flight_filename)

        logger.debug(f"Marked flight as processed: {flight_filename}")

    def mark_date_processed(
        self,
        date_str: str
    ) -> None:
        """
        Mark a date as having flights processed.

        Args:
            date_str: Date in YYYY-MM-DD format
        """
        if date_str not in self.state['processed_dates']:
            self.state['processed_dates'][date_str] = {
                'flights': [],
                
                'last_processed': None
            }        self.state['processed_dates'][date_str]['last_processed'] = datetime.utcnow().isoformat() + 'Z'

        logger.debug(f"Marked date as processed: {date_str}")

    def get_processed_flight_count(self) -> int:
        """Get total number of processed flights"""
        return len(self.state['processed_flights'])

    def get_processed_date_count(self) -> int:
        """Get total number of processed dates"""
        return len(self.state['processed_dates'])

    def get_summary(self) -> str:
        """
        Get human-readable summary of state.

        Returns:
            Summary string
        """
        total_flights = len(self.state['processed_flights'])
        total_dates = len(self.state['processed_dates'])
        dates_with_tiles = len(self.state['processed_dates'])

        summary = f"Processing State for {self.airport_code}\n"
        summary += f"  Total flights processed: {total_flights}\n"
        summary += f"  Total dates tracked: {total_dates}\n"
        if self.state['last_updated']:
            summary += f"  Last updated: {self.state['last_updated']}\n"

        return summary

    def reset(self) -> None:
        """Reset state to empty"""
        logger.warning("Resetting state to empty")
        self.state = self._create_empty_state()

    def get_flights_for_date(self, date_str: str) -> List[str]:
        """
        Get list of processed flights for a specific date.

        Args:
            date_str: Date in YYYY-MM-DD format

        Returns:
            List of flight filenames
        """
        date_state = self.state['processed_dates'].get(date_str, {})
        return date_state.get('flights', [])


def main():
    """CLI for inspecting/managing state"""
    import argparse

    parser = argparse.ArgumentParser(description='Manage processing state')
    parser.add_argument('--airport-code', '-a', required=True, help='Airport code')
    parser.add_argument('--state-file', help='Path to state file')
    parser.add_argument('--action', choices=['show', 'reset'], default='show',
                        help='Action to perform')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(message)s')

    state = ProcessingState(args.airport_code, args.state_file)

    if args.action == 'show':
        print(state.get_summary())

        # Show recent dates
        if state.state['processed_dates']:
            print("\nRecent dates:")
            sorted_dates = sorted(state.state['processed_dates'].keys(), reverse=True)
            for date_str in sorted_dates[:10]:
                date_state = state.state['processed_dates'][date_str]
                tiles = "N/A"  # Satellite tiles removed (served from NASA GIBS)
                flight_count = len(date_state.get('flights', []))
                print(f"  {date_str}: {flight_count} flights, tiles: {tiles}")

    elif args.action == 'reset':
        confirm = input(f"Reset state for {args.airport_code}? (yes/no): ")
        if confirm.lower() == 'yes':
            state.reset()
            state.save()
            print("State reset successfully")
        else:
            print("Cancelled")


if __name__ == '__main__':
    main()
