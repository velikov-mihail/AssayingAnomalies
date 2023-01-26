function [out]=dblebarmap(long,lat,var1,var2,varargin)
% PURPOSE: This function links a map and two bar plots
%------------------------------------------------------------------------
% USAGE: out=dblebarmap(long,lat,var1,var2,carte,label,symbol)
%   where : 
%           long = n x 1 vector of coordinates on the first axis
%           lat = n x 1 vector of coordinates on the second axis
%           var1 = n x 1 vector of the first variable to study
%           var2 = n x 1 vector of the second variable to study
%           carte = n x 2 optionnal matrix giving the polygons of the edges of the spatial units
%           label = n x 1 optionnal variable used to label selected observations
%           symbol = * symbol=1 : selected spatial units are marked with a different symbol
%                    * symbol=0 : selected spatial units are marked with a different color only (default)
%------------------------------------------------------------------------
% OUTPUTS: out = (n x 1) 0-1 variable: selected spatial units are marked with a 1  
%------------------------------------------------------------------------
% MANUAL: Select points on the map by clicking with the left mouse button
%         Select bars on a bar plot by clicking with the left mouse button
%         You can select points inside a polygon on the map: - right click to set the first point of the polygon
%                                                            - left click to set the other points
%                                                            - right click to close the polygon
%         Selection is lost when you switch graph
%         To quit, click the middle button or press 'q'
% -----------------------------------------------------------------------
% uses selectmap.m, selectstat.m
%------------------------------------------------------------------------
% Christine Thomas-Agnan, Anne Ruiz-Gazen, Julien Moutel
% June 2003
% Université de Toulouse I, Toulouse, France
% cthomas@cict.fr


close all;
figure(1);
set(figure(1),'Units','Normalized','Position',[0.0031 0.0957 0.9945 0.7539]);
set(figure(1),'Units','Pixel');
obs=zeros(size(long,1),1);
vectx=[];
vecty=[];
name1=inputname(3);
name2=inputname(4);
symbol=0;
%creation d'un menu pour sauver
labels= str2mat(...
    '&File', ...
    '>&Save' ...
    );
calls= str2mat(...
    '',...
    'save dblbarfich  out -ascii' ...
    );
makemenu(figure(1),labels,calls);
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

% handle the optionnal parameters
if ~isempty(varargin) 
    t=size(varargin,2);
    if  ~isempty(varargin{1})
        carte=varargin{1};
        c=1;
    else 
        c=0;
    end;
    if  t>=2 & ~isempty(varargin{2})
        label=varargin{2};
        l=1;
    else 
        l=0;
    end;
    if t==3 & ~isempty(varargin{3})
        symbol=varargin{3};
    end;
else
    c=0;
    l=0;
end;
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

% Trace the map
Axis1=subplot(1,2,1);
if c==1
    plot(carte(:,1),carte(:,2),'Color',[0.8 0.5 0.6]);
end;
hold on;
plot(long,lat,'b.');
axis equal;
title('Map');
Xlim1=get(Axis1,'XLim');
Ylim1=get(Axis1,'YLim');

% Trace the histograms

Axis2=subplot(2,2,2);
vsort=sort(var1);
edge=sort(var1)';
edge2=[edge,inf];
N1=histc(var1,edge2);
N1=N1(1:end-1);
N=N1(find(N1~=0));
edge=edge(find(N1~=0));
edgeaff=[0:length(edge)-1];
edge2=[edge,inf];
%bar(edgeaff,N,'b');
bar(edgeaff,N,'histc');
set(Axis2,'Xlim',[-1,edgeaff(end)+1]);
set(Axis2,'Xtick',[0:length(vsort(find(N1~=0)))-1]);
set(Axis2,'Xticklabel',vsort(find(N1~=0)));
set(Axis2,'FontSize',6);
xlabel(name1);
axis manual;

Axis3=subplot(2,2,4);
vsort2=sort(var2);
edge3=sort(var2)';
edge4=[edge3,inf];
Nter=histc(var2,edge4);
Nter=Nter(1:end-1);
Nbis=Nter(find(Nter~=0));
edge3=edge3(find(Nter~=0));
edgeaff2=[0:length(edge3)-1];
edge4=[edge3,inf];
%bar(edgeaff2,Nbis,'b');
bar(edgeaff2,Nbis,'histc');
set(Axis3,'Xlim',[-1,edgeaff2(end)+1]);
set(Axis3,'Xtick',[0:length(vsort2(find(Nter~=0)))-1]);
set(Axis3,'Xticklabel',vsort2(find(Nter~=0)));
set(Axis3,'FontSize',6);

xlabel(name2);
axis manual;
subplot(Axis1);
axis manual;
Xlim2=get(Axis2,'XLim');
Ylim2=get(Axis2,'YLim');
Xlim3=get(Axis3,'XLim');
Ylim3=get(Axis3,'YLim');


% Main loop
maptest=0;
bartest1=0;
bartest2=0;
BUTTON=0;
while BUTTON~=2 & BUTTON~=113 % Stop when the user push the middle button or press 'q'
    Posfig=get(1,'Position');
    PosAx1=get(Axis1,'Position');
    PosAx2=get(Axis2,'Position');
    PosAx3=get(Axis3,'Position');
    %redraw the graphs
    subplot(Axis2);
    hold on;
    cla;
    bar(edgeaff,N,0.6,'b');
    Iselect=find(obs==1);
    Iunselect=find(obs==0);
    if ~isempty(Iselect)
        if maptest==1
            N3=histc(var1(Iselect),edge2);
            N3=N3(1:end-1);
            bar(edgeaff,N3,0.6,'r');
        elseif bartest1==1
            N3=histc(var1(Iselect),edge2);
            N3=N3(1:end-1);
            bar(edgeaff,N3,0.6,'m');
        elseif bartest2==1
            N3=histc(var1(Iselect),edge2);
            N3=N3(1:end-1);
            bar(edgeaff,N3,0.6,'g');
        end;
    end;
    hold off;
    
    subplot(Axis3);
    hold on;
    cla;
    bar(edgeaff2,Nbis,0.6,'b');
    Iselect=find(obs==1);
    Iunselect=find(obs==0);
    if ~isempty(Iselect)
        if maptest==1
            N3=histc(var2(Iselect),edge4);
            N3=N3(1:end-1);
            bar(edgeaff2,N3,0.6,'r');
        elseif bartest1==1
            N3=histc(var2(Iselect),edge4);
            N3=N3(1:end-1);
            bar(edgeaff2,N3,0.6,'m');
        elseif bartest2==1
            N3=histc(var2(Iselect),edge4);
            N3=N3(1:end-1);
            bar(edgeaff2,N3,0.6,'g');
        end;
    end;
    hold off;
    
    subplot(Axis1);
    hold on;
    cla;
    if c==1
            plot(carte(:,1),carte(:,2),'Color',[0.8 0.5 0.6]);
    end;
    if ~isempty(Iunselect)
      plot(long(Iunselect),lat(Iunselect),'b.');
    end;
    if ~isempty(Iselect)
        if maptest==1
            if symbol==1
                plot(long(Iselect),lat(Iselect),'b*');  
            else
                plot(long(Iselect),lat(Iselect),'r.');      
            end;
            if ~isempty(vectx)
                plot(vectx,vecty,'k');
            end;
        elseif bartest1==1
            if symbol==1
                plot(long(Iselect),lat(Iselect),'bo');  
            else
                plot(long(Iselect),lat(Iselect),'m.');      
            end;
        elseif bartest2==1
            if symbol==1
                plot(long(Iselect),lat(Iselect),'bd');  
            else
                plot(long(Iselect),lat(Iselect),'g.');      
            end;
        end;
        if l==1
            Htex=text(long(Iselect),lat(Iselect),num2str(label(Iselect)));
            set(Htex,'FontSize',8);
        end;
    end;   
    
    hold off;
    %%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    
    [x,y,BUTTON]=ginput(1);
    currentpoint=get(1,'CurrentPoint');
    % map selection
    if (currentpoint(1)>=PosAx1(1)*Posfig(3)) & (currentpoint(1)<=(PosAx1(1)+PosAx1(3))*Posfig(3)) & (currentpoint(2)>=PosAx1(2)*Posfig(4)) & (currentpoint(2)<=(PosAx1(2)+PosAx1(4))*Posfig(4))
        if maptest==0     
            maptest=1;
            bartest1=0;
            bartest2=0;
            obs=zeros(size(long,1),1);
        end;
        % point selection
        if BUTTON~=3 & BUTTON~=2
            [obs,vectx,vecty]=selectmap(lat,long,obs,x,y,'point');
        %%%%%%%%%%%%%%%%%
        % polygon selection
        elseif BUTTON==3 
            [obs,vectx,vecty]=selectmap(lat,long,obs,x,y,'poly');
        end;
        %%%%%%%%%%%%%%%%%
    % histogram 1 selection
    elseif (currentpoint(1)>=PosAx2(1)*Posfig(3)) & (currentpoint(1)<=(PosAx2(1)+PosAx2(3))*Posfig(3)) & (currentpoint(2)>=PosAx2(2)*Posfig(4)) & (currentpoint(2)<=(PosAx2(2)+PosAx2(4))*Posfig(4))
        if bartest1==0
            bartest1=1;
            maptest=0;
            bartest2=0;
            obs=zeros(size(long,1),1);
        end;
        % bar selection
        if BUTTON~=3 & BUTTON~=2 
            obs=selectstat('bar',obs,var1,edge2,N,x,y,edgeaff);
        end;
        %%%%%%%%%%%%%%%
    % histogram 2 selection
    elseif (currentpoint(1)>=PosAx3(1)*Posfig(3)) & (currentpoint(1)<=(PosAx3(1)+PosAx3(3))*Posfig(3)) & (currentpoint(2)>=PosAx3(2)*Posfig(4)) & (currentpoint(2)<=(PosAx3(2)+PosAx3(4))*Posfig(4))
        if bartest2==0
            bartest2=1;
            maptest=0;
            bartest1=0;
            obs=zeros(size(long,1),1);
        end;
        % bar selection
        if BUTTON~=3 & BUTTON~=2 
            obs=selectstat('bar',obs,var2,edge4,Nbis,x,y,edgeaff2);
        end;
    end;
    %%%%%%%%%%%%%%%%%%
end;
out=obs;

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%