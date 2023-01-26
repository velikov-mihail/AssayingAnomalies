function vov=makeKyleObizhaeva()
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% This functions create the VoV Effective Spread (!!!) measure from Kyle
% and Obizhaeva (WP, 2017) following the implementation of Fong, Holden,
% and Tobek (WP, 2018)

load dvol
load dret
load ddates
load dates
load ret
load dprc

a=8.0;
b=2/3;
c=1/3;

dvol=dvol.*abs(dprc);

% Inflation
cpi=nan(size(dates));
endDate=[num2str(floor(dates(end)/100)),'-12-31'];
fredStruct=getFredData('CPIAUCNS',[],endDate,'lin','m','eop');
fredDates=datetime(fredStruct.Data(:,1),'ConvertFrom','datenum');
fredDates=100*year(fredDates)+month(fredDates);
[~,ind_dates,ind_fred]=intersect(dates,fredDates,'legacy');
cpi(ind_dates)=fredStruct.Data(ind_fred,2);
cpi=cpi/cpi(find(dates==200001)); % That's FHT's (2018) normalization 

vov=nan(size(ret));

for i=1:length(dates)
    month_ind=find(floor(ddates/100)==dates(i));
    hor_ind=find(sum(dvol(month_ind,:)>0,1)>=5 & sum(abs(dret(month_ind,:))>0,1)>=11);
    num= a * (nanstd(dret(month_ind,hor_ind),0,1).^b);
    denom=(nanmean(dvol(month_ind,hor_ind),1)/cpi(i)).^c;
    vov(i,hor_ind)=(num)./(denom);
end

fprintf('Done with VoV at:\n');
disp(datetime('now'));
